1import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
2import { Play, Pause, RotateCcw, Volume2, VolumeX, Sliders, Music, Radio, Waves, Shield, Skull, BookOpen, Download, Copy, Check, FileText, Sparkles, Layers, Trophy, Swords, AlertTriangle, CheckCircle, ArrowLeft, Compass } from "lucide-react";
3
4interface Note {
5  pitch: string;
6  duration: number; // in beats (quarter = 1.0)
7  staccato?: boolean;
8}
9
10// 128-beat (32 measures of 4/4) 3-Voice Polyphonic Fugue in D minor
11// Strict Consonant Harmony: No dissonant clashes; all sept chords resolve strictly to Dominant chords (A Major).
12const FUGUE_SECTIONS = [
13  { startBar: 1, endBar: 4, name: "Exposition: Voice 1 Subject (D minor)", description: "Solemn opening statement in the Alto register" },
14  { startBar: 5, endBar: 8, name: "Voice 2 Answer in A minor (Dominant)", description: "Soprano entry with consonant counterpoint in Alto" },
15  { startBar: 9, endBar: 12, name: "Voice 3 Bass Entry in D minor", description: "Consonant 3-part triads; sept chord resolves to dominant" },
16  { startBar: 13, endBar: 16, name: "Episode I: Modulation to F Major", description: "Consonant circle-of-fifths with staccato walking bass" },
17  { startBar: 17, endBar: 20, name: "Middle Entry (F Major & G minor)", description: "Consonant triads with ii7 sept resolving to dominant A" },
18  { startBar: 21, endBar: 24, name: "Episode II: Dominant Preparation", description: "Consonant motion with sept chord resolution to A dominant" },
19  { startBar: 25, endBar: 28, name: "Stretto Climax & Dominant Drive", description: "Full 3-voice consonant chords resolving to dominant A" },
20  { startBar: 29, endBar: 32, name: "Coda & Pure Minor Tonic Cadence", description: "Sept to dominant resolution ending on dark, brooding pure minor triad" },
21];
22
23// Harmonic lookup table per bar/beat to display the active chord & resolution
24interface ChordInfo {
25  bar: number;
26  beatInBar: number; // 1 to 4
27  chordName: string;
28  isDominant?: boolean;
29  isSeptResolution?: boolean;
30}
31
32const CHORD_TIMELINE: { startBeat: number; endBeat: number; chord: string; isDominant?: boolean; isSept?: boolean }[] = [
33  // Bars 1-4
34  { startBeat: 0, endBeat: 16, chord: "D minor (Tonic Solo)" },
35  // Bars 5-8
36  { startBeat: 16, endBeat: 24, chord: "A minor (Dominant key)" },
37  { startBeat: 24, endBeat: 26, chord: "F / D minor Consonance" },
38  { startBeat: 26, endBeat: 27, chord: "Sept harmony (Em7)", isSept: true },
39  { startBeat: 27, endBeat: 28, chord: "A Major (Dominant resolved)", isDominant: true },
40  { startBeat: 28, endBeat: 30, chord: "D minor (Tonic)" },
41  { startBeat: 30, endBeat: 32, chord: "A Major (Dominant resolved)", isDominant: true },
42  // Bars 9-12
43  { startBeat: 32, endBeat: 36, chord: "D minor Triad (Root)" },
44  { startBeat: 36, endBeat: 38, chord: "G minor Triad (iv)" },
45  { startBeat: 38, endBeat: 40, chord: "A Major Triad (Dominant V)", isDominant: true },
46  { startBeat: 40, endBeat: 42, chord: "F Major Triad (Relative III)" },
47  { startBeat: 42, endBeat: 43, chord: "Bb Major Triad (VI)" },
48  { startBeat: 43, endBeat: 44, chord: "D minor Triad (i)" },
49  { startBeat: 44, endBeat: 46, chord: "Sept chord (Gm7 / ii7)", isSept: true },
50  { startBeat: 46, endBeat: 48, chord: "A Major (Dominant V resolved)", isDominant: true },
51  // Bars 13-16
52  { startBeat: 48, endBeat: 49, chord: "D minor Triad" },
53  { startBeat: 49, endBeat: 50, chord: "G minor Triad" },
54  { startBeat: 50, endBeat: 51, chord: "C Major Triad" },
55  { startBeat: 51, endBeat: 52, chord: "F Major Triad" },
56  { startBeat: 52, endBeat: 53, chord: "Bb Major Triad" },
57  { startBeat: 53, endBeat: 54, chord: "G minor Triad" },
58  { startBeat: 54, endBeat: 56, chord: "C Major Triad (V of F)" },
59  { startBeat: 56, endBeat: 58, chord: "F Major Triad" },
60  { startBeat: 58, endBeat: 59, chord: "A minor Triad" },
61  { startBeat: 59, endBeat: 60, chord: "C Major Triad" },
62  { startBeat: 60, endBeat: 62, chord: "Sept chord (Gm7)", isSept: true },
63  { startBeat: 62, endBeat: 64, chord: "A Major (Dominant V resolved)", isDominant: true },
64  // Bars 17-20
65  { startBeat: 64, endBeat: 66, chord: "F Major Triad" },
66  { startBeat: 66, endBeat: 68, chord: "C Major Triad" },
67  { startBeat: 68, endBeat: 70, chord: "D minor Triad" },
68  { startBeat: 70, endBeat: 72, chord: "Bb Major Triad" },
69  { startBeat: 72, endBeat: 74, chord: "G minor Triad" },
70  { startBeat: 74, endBeat: 76, chord: "D minor Triad" },
71  { startBeat: 76, endBeat: 78, chord: "Sept chord (Em7)", isSept: true },
72  { startBeat: 78, endBeat: 80, chord: "A Major (Dominant V resolved)", isDominant: true },
73  // Bars 21-24
74  { startBeat: 80, endBeat: 82, chord: "D minor Triad" },
75  { startBeat: 82, endBeat: 84, chord: "F Major Triad" },
76  { startBeat: 84, endBeat: 86, chord: "G minor Triad" },
77  { startBeat: 86, endBeat: 88, chord: "Bb Major Triad" },
78  { startBeat: 88, endBeat: 90, chord: "Sept chord (Em7)", isSept: true },
79  { startBeat: 90, endBeat: 92, chord: "A Major (Dominant V resolved)", isDominant: true },
80  { startBeat: 92, endBeat: 96, chord: "A Major Pedal (Dominant V)", isDominant: true },
81  // Bars 25-28
82  { startBeat: 96, endBeat: 100, chord: "D minor Triad (Stretto Tonic)" },
83  { startBeat: 100, endBeat: 102, chord: "D minor Triad" },
84  { startBeat: 102, endBeat: 104, chord: "F Major Triad" },
85  { startBeat: 104, endBeat: 106, chord: "G minor Triad" },
86  { startBeat: 106, endBeat: 108, chord: "Bb Major Triad" },
87  { startBeat: 108, endBeat: 110, chord: "Sept chord (Em7)", isSept: true },
88  { startBeat: 110, endBeat: 112, chord: "A Major (Dominant V resolved)", isDominant: true },
89  // Bars 29-32
90  { startBeat: 112, endBeat: 114, chord: "G minor Triad" },
91  { startBeat: 114, endBeat: 116, chord: "D minor Triad" },
92  { startBeat: 116, endBeat: 118, chord: "Sept chord (Em7)", isSept: true },
93  { startBeat: 118, endBeat: 120, chord: "A Major (Dominant V resolved)", isDominant: true },
94  { startBeat: 120, endBeat: 124, chord: "A Major Cadence (Dominant V)", isDominant: true },
95  { startBeat: 124, endBeat: 128, chord: "D minor Triad (Dark Tonic Cadence)" },
96];
97
98// Theme Variant Type & Definitions
99export interface ThemeVariant {
100  id: "d_minor_crypt" | "f_minor_lament" | "f_minor_staccato_theme" | "c_minor_passacaglia" | "g_minor_fantasia" | "a_minor_ricercar" | "e_minor_toccata";
101  name: string;
102  key: string;
103  keyName: string;
104  subtitle: string;
105  description: string;
106  v1: Note[];
107  v2: Note[];
108  v3: Note[];
109  chords: { startBeat: number; endBeat: number; chord: string; isDominant?: boolean; isSept?: boolean }[];
110}
111
112export interface GameCue {
113  id: "dungeon_crawl" | "dangerous" | "boss_fight" | "level_complete" | "game_win" | "game_over";
114  name: string;
115  subtitle: string;
116  icon: "crawl" | "skull" | "trophy" | "swords" | "danger" | "check";
117  totalBeats: number;
118  loop: boolean;
119  defaultBpm: number;
120  v1: Note[];
121  v2: Note[];
122  v3: Note[];
123  chords: { startBeat: number; endBeat: number; chord: string; isDominant?: boolean; isSept?: boolean }[];
124}
125
126// ---------------------------------------------------------
127// 6 SHORT F MINOR GAME CUES & THEMES FOR TOME OF THE DEAD (ORDERED FOR DUNGEON GAMEPLAY)
128// 1. Dungeon Crawl (Exploration)
129// 2. Dangerous (Stealth / Low Health Tension)
130// 3. Boss Fight (Lich Combat)
131// 4. Level Complete (Area Cleared)
132// 5. Game Win (Relic Triumph)
133// 6. Game Over (Funeral Lament)
134// ---------------------------------------------------------
135const GAME_CUES: GameCue[] = [
136  {
137    id: "dungeon_crawl",
138    name: "Dungeon Crawl",
139    subtitle: "Walking in the Dungeon • Cautious Footsteps & Exploration (Fm)",
140    icon: "crawl",
141    totalBeats: 16,
142    loop: true,
143    defaultBpm: 72,
144    v1: [
145      // Bar 1: Cautious Footfall in F minor
146      { pitch: "C4", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
147      { pitch: "Ab4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
148      // Bar 2: Deepening Shadows (Db Major to Bb minor)
149      { pitch: "F4", duration: 1.0 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "Db5", duration: 0.5 },
150      { pitch: "C5", duration: 1.0 }, { pitch: "Bb4", duration: 1.0 },
151      // Bar 3: Hazard Ahead (Sept resolving to Dominant C Major)
152      { pitch: "Bb4", duration: 1.0 }, { pitch: "Db5", duration: 0.5 }, { pitch: "Bb4", duration: 0.5 },
153      { pitch: "G4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
154      // Bar 4: Re-centering in F minor (Seamless Loop)
155      { pitch: "F4", duration: 1.0 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
156      { pitch: "C5", duration: 1.0 }, { pitch: "Ab4", duration: 1.0 },
157    ],
158    v2: [
159      // Bar 1: Ethereal Dungeon Air
160      { pitch: "Ab4", duration: 1.0 }, { pitch: "C5", duration: 1.0 },
161      { pitch: "F5", duration: 1.0 }, { pitch: "C5", duration: 1.0 },
162      // Bar 2
163      { pitch: "Db5", duration: 1.0 }, { pitch: "F5", duration: 1.0 },
164      { pitch: "F5", duration: 0.5 }, { pitch: "Db5", duration: 0.5 }, { pitch: "F5", duration: 1.0 },
165      // Bar 3: Dominant V
166      { pitch: "G4", duration: 1.0 }, { pitch: "Bb4", duration: 1.0 },
167      { pitch: "C5", duration: 1.0 }, { pitch: "G4", duration: 1.0 },
168      // Bar 4: Return to Fm
169      { pitch: "Ab4", duration: 1.0 }, { pitch: "C5", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 },
170      { pitch: "F5", duration: 1.0 }, { pitch: "C5", duration: 1.0 },
171    ],
172    v3: [
173      // Bar 1: Steady Walking Bass
174      { pitch: "F2", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
175      { pitch: "Ab2", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
176      // Bar 2: Descending Stone Steps
177      { pitch: "Db3", duration: 1.0 }, { pitch: "Ab2", duration: 1.0 },
178      { pitch: "Bb2", duration: 1.0 }, { pitch: "F2", duration: 1.0 },
179      // Bar 3: Sept to Dominant V
180      { pitch: "G2", duration: 1.0 }, { pitch: "Bb2", duration: 1.0 },
181      { pitch: "C3", duration: 1.0 }, { pitch: "E2", duration: 1.0 },
182      // Bar 4: Loop anchor
183      { pitch: "F2", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
184      { pitch: "F2", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
185    ],
186    chords: [
187      { startBeat: 0, endBeat: 4, chord: "F minor (Walking Footsteps)" },
188      { startBeat: 4, endBeat: 8, chord: "Db Major to Bb minor (Stone Steps)" },
189      { startBeat: 8, endBeat: 12, chord: "Sept chord → C Major Dominant", isDominant: true },
190      { startBeat: 12, endBeat: 16, chord: "F minor (Crypt Anchor)" },
191    ],
192  },
193  {
194    id: "dangerous",
195    name: "Dangerous",
196    subtitle: "Creeping Dread • Ominous Low-Health / Stealth Suspense",
197    icon: "danger",
198    totalBeats: 8,
199    loop: true,
200    defaultBpm: 68,
201    v1: [
202      { pitch: "F4", duration: 1.0 }, { pitch: "Gb4", duration: 1.0 }, { pitch: "F4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
203      { pitch: "F4", duration: 1.0 }, { pitch: "Ab4", duration: 1.0 }, { pitch: "G4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
204    ],
205    v2: [
206      { pitch: "C5", duration: 1.0 }, { pitch: "Db5", duration: 1.0 }, { pitch: "C5", duration: 1.0 }, { pitch: "Bb4", duration: 1.0 },
207      { pitch: "C5", duration: 1.0 }, { pitch: "C5", duration: 1.0 }, { pitch: "E4", duration: 1.0 }, { pitch: "G4", duration: 1.0 },
208    ],
209    v3: [
210      { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
211      { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
212      { pitch: "Db2", duration: 1.0 }, { pitch: "Bb2", duration: 1.0 }, { pitch: "C2", duration: 1.0 }, { pitch: "C2", duration: 1.0 },
213    ],
214    chords: [
215      { startBeat: 0, endBeat: 2, chord: "F minor (Heartbeat Pulse)" },
216      { startBeat: 2, endBeat: 4, chord: "Neapolitan Gb / C Dominant Tension", isDominant: true },
217      { startBeat: 4, endBeat: 6, chord: "F minor Creeping Shadow" },
218      { startBeat: 6, endBeat: 8, chord: "C Dominant Suspension", isDominant: true },
219    ],
220  },
221  {
222    id: "boss_fight",
223    name: "Boss Fight",
224    subtitle: "Lich Lord Battle • Driving Baroque Combat Ostinato (Fm)",
225    icon: "swords",
226    totalBeats: 16,
227    loop: true,
228    defaultBpm: 106,
229    v1: [
230      { pitch: "F4", duration: 0.5 }, { pitch: "C4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 },
231      { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "C4", duration: 0.5 },
232      { pitch: "Ab4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 0.5 },
233      { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "C4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
234      { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "Db5", duration: 0.5 },
235      { pitch: "C5", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
236      { pitch: "Ab4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
237      { pitch: "F4", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
238    ],
239    v2: [
240      { pitch: "C5", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "F5", duration: 0.5 },
241      { pitch: "E5", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
242      { pitch: "F5", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "F5", duration: 0.5 }, { pitch: "Ab5", duration: 0.5 },
243      { pitch: "G5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
244      { pitch: "Ab5", duration: 0.5 }, { pitch: "F5", duration: 0.5 }, { pitch: "Ab5", duration: 0.5 }, { pitch: "Bb5", duration: 0.5 },
245      { pitch: "Ab5", duration: 0.5 }, { pitch: "F5", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "E5", duration: 0.5 },
246      { pitch: "F5", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "C5", duration: 0.5 },
247      { pitch: "C5", duration: 1.0 }, { pitch: "C5", duration: 1.0 },
248    ],
249    v3: [
250      { pitch: "F2", duration: 0.5 }, { pitch: "F3", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F3", duration: 0.5 },
251      { pitch: "C3", duration: 0.5 }, { pitch: "G2", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
252      { pitch: "F2", duration: 0.5 }, { pitch: "F3", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "F3", duration: 0.5 },
253      { pitch: "C3", duration: 0.5 }, { pitch: "E2", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
254      { pitch: "Db3", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "Db3", duration: 0.5 }, { pitch: "Bb2", duration: 0.5 },
255      { pitch: "F2", duration: 0.5 }, { pitch: "Ab2", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
256      { pitch: "F2", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
257      { pitch: "F2", duration: 1.0 }, { pitch: "F2", duration: 1.0 },
258    ],
259    chords: [
260      { startBeat: 0, endBeat: 4, chord: "F minor Battle Ostinato" },
261      { startBeat: 4, endBeat: 8, chord: "C Major Dominant Attack", isDominant: true },
262      { startBeat: 8, endBeat: 12, chord: "Db Major to Bb minor Drive" },
263      { startBeat: 12, endBeat: 14, chord: "C Major Dominant Climax", isDominant: true },
264      { startBeat: 14, endBeat: 16, chord: "F minor Battle Tonic" },
265    ],
266  },
267  {
268    id: "level_complete",
269    name: "Level Complete",
270    subtitle: "Crypt Cleared • Rewarding Baroque Cadence & Fanfare",
271    icon: "check",
272    totalBeats: 8,
273    loop: false,
274    defaultBpm: 78,
275    v1: [
276      { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
277      { pitch: "Bb4", duration: 0.5 }, { pitch: "Db5", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
278      { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
279      { pitch: "F4", duration: 2.0 },
280    ],
281    v2: [
282      { pitch: "C5", duration: 0.5 }, { pitch: "F5", duration: 0.5 }, { pitch: "Ab5", duration: 1.0 },
283      { pitch: "F5", duration: 0.5 }, { pitch: "Bb5", duration: 0.5 }, { pitch: "Ab5", duration: 1.0 },
284      { pitch: "F5", duration: 0.5 }, { pitch: "Ab5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "G5", duration: 0.5 },
285      { pitch: "F5", duration: 2.0 },
286    ],
287    v3: [
288      { pitch: "F2", duration: 1.0 }, { pitch: "Ab2", duration: 1.0 },
289      { pitch: "Db3", duration: 1.0 }, { pitch: "F3", duration: 1.0 },
290      { pitch: "Db3", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
291      { pitch: "F2", duration: 2.0 },
292    ],
293    chords: [
294      { startBeat: 0, endBeat: 2, chord: "F minor Cleared Flourish" },
295      { startBeat: 2, endBeat: 4, chord: "Db Major Victory Ascent" },
296      { startBeat: 4, endBeat: 6, chord: "C Major Cadential Drive", isDominant: true },
297      { startBeat: 6, endBeat: 8, chord: "F minor (Grand Completion)" },
298    ],
299  },
300  {
301    id: "game_win",
302    name: "Game Win",
303    subtitle: "Triumph of the Relic • Victorious Baroque Fanfare in Fm",
304    icon: "trophy",
305    totalBeats: 8,
306    loop: false,
307    defaultBpm: 84,
308    v1: [
309      { pitch: "C4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 1.0 },
310      { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
311      { pitch: "Db5", duration: 1.0 }, { pitch: "Bb4", duration: 1.0 },
312      { pitch: "C5", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
313    ],
314    v2: [
315      { pitch: "F4", duration: 0.5 }, { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
316      { pitch: "Ab4", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "F5", duration: 1.0 },
317      { pitch: "F5", duration: 1.0 }, { pitch: "G4", duration: 1.0 },
318      { pitch: "E4", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
319    ],
320    v3: [
321      { pitch: "F2", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
322      { pitch: "F3", duration: 1.0 }, { pitch: "Ab2", duration: 1.0 },
323      { pitch: "Bb2", duration: 1.0 }, { pitch: "Db3", duration: 1.0 },
324      { pitch: "C3", duration: 1.0 }, { pitch: "F2", duration: 1.0 },
325    ],
326    chords: [
327      { startBeat: 0, endBeat: 2, chord: "F minor Fanfare" },
328      { startBeat: 2, endBeat: 4, chord: "Ab Major Triumph" },
329      { startBeat: 4, endBeat: 6, chord: "Db Major to Bb minor" },
330      { startBeat: 6, endBeat: 7, chord: "C Major (Dominant V)", isDominant: true },
331      { startBeat: 7, endBeat: 8, chord: "F minor (Noble Resolution)" },
332    ],
333  },
334  {
335    id: "game_over",
336    name: "Game Over",
337    subtitle: "Lament of the Fallen • Mournful F minor Funeral Cadence",
338    icon: "skull",
339    totalBeats: 8,
340    loop: false,
341    defaultBpm: 66,
342    v1: [
343      { pitch: "F4", duration: 1.0 }, { pitch: "Ab4", duration: 1.0 }, { pitch: "C5", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
344      { pitch: "F4", duration: 1.0 }, { pitch: "Db4", duration: 1.0 }, { pitch: "C4", duration: 1.0 }, { pitch: "F3", duration: 1.0 },
345    ],
346    v2: [
347      { pitch: "Ab4", duration: 1.0 }, { pitch: "C5", duration: 1.0 }, { pitch: "F5", duration: 1.0 }, { pitch: "G4", duration: 1.0 },
348      { pitch: "Ab4", duration: 1.0 }, { pitch: "F4", duration: 1.0 }, { pitch: "E4", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
349    ],
350    v3: [
351      { pitch: "F2", duration: 1.0 }, { pitch: "C3", duration: 1.0 }, { pitch: "F3", duration: 1.0 }, { pitch: "C3", duration: 1.0 },
352      { pitch: "Db3", duration: 1.0 }, { pitch: "Bb2", duration: 1.0 }, { pitch: "C3", duration: 1.0 }, { pitch: "F2", duration: 1.0 },
353    ],
354    chords: [
355      { startBeat: 0, endBeat: 2, chord: "F minor (Solemn Toll)" },
356      { startBeat: 2, endBeat: 4, chord: "C Major (Dominant V)", isDominant: true },
357      { startBeat: 4, endBeat: 6, chord: "Db Major to Bb minor" },
358      { startBeat: 6, endBeat: 7, chord: "C Major (Dominant V)", isDominant: true },
359      { startBeat: 7, endBeat: 8, chord: "F minor (Death Resolution)" },
360    ],
361  },
362];
363
364// ---------------------------------------------------------
365// BASE MASTER PIECE (D minor)
366// PURE LEGATO ONLY: All staccato articulations removed!
367// Continuous accompaniment from Bar 1 Beat 1 across all 3 voices!
368// ---------------------------------------------------------
369const BASE_V1_LEGATO: Note[] = [
370  // Bars 1-4: Subject in D minor with legato phrasing
371  { pitch: "D4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
372  { pitch: "D5", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
373  { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
374  { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
375  { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
376  { pitch: "D4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
377  { pitch: "Bb4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "Bb4", duration: 0.5 },
378  { pitch: "A4", duration: 1.0 }, { pitch: "E4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
379
380  // Bars 5-8: Legato Countersubject
381  { pitch: "C4", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
382  { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
383  { pitch: "A4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
384  { pitch: "E4", duration: 1.0 }, { pitch: "C#4", duration: 1.0 },
385  { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "D4", duration: 1.0 },
386  { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "A3", duration: 1.0 },
387  { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
388  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
389
390  // Bars 9-12: Full 3-Voice Legato Entry
391  { pitch: "F4", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
392  { pitch: "A4", duration: 1.0 }, { pitch: "F4", duration: 1.0 },
393  { pitch: "D4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
394  { pitch: "C#4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
395  { pitch: "A4", duration: 1.0 }, { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
396  { pitch: "D4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
397  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
398  { pitch: "E4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
399
400  // Bars 13-16: Episode I (Legato Flow)
401  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 1.0 }, { pitch: "E4", duration: 1.0 }, { pitch: "C4", duration: 1.0 },
402  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
403  { pitch: "E4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
404  { pitch: "A4", duration: 1.0 }, { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
405  { pitch: "C4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
406  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
407  { pitch: "E4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
408
409  // Bars 17-20: Middle Entry
410  { pitch: "A3", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
411  { pitch: "G3", duration: 1.0 }, { pitch: "C4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
412  { pitch: "F3", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
413  { pitch: "D4", duration: 1.0 }, { pitch: "Bb3", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
414  { pitch: "D4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
415  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
416  { pitch: "G3", duration: 1.0 }, { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
417  { pitch: "A4", duration: 1.0 }, { pitch: "C#4", duration: 1.0 },
418
419  // Bars 21-24: Episode II
420  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
421  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
422  { pitch: "D4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 1.0 },
423  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
424  { pitch: "G3", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "G3", duration: 1.0 },
425  { pitch: "C#4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
426  { pitch: "E4", duration: 0.5 }, { pitch: "C#4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
427  { pitch: "C#4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
428
429  // Bars 25-28: Stretto
430  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
431  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
432  { pitch: "A3", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
433  { pitch: "C4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
434  { pitch: "D4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
435  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
436  { pitch: "G3", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "G3", duration: 1.0 },
437  { pitch: "C#4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
438
439  // Bars 29-32: Coda & Pure Minor Cadence
440  { pitch: "D4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 1.0 },
441  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
442  { pitch: "G3", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "G3", duration: 1.0 },
443  { pitch: "C#4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
444  { pitch: "E4", duration: 0.5 }, { pitch: "C#4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
445  { pitch: "A4", duration: 0.5 }, { pitch: "C#4", duration: 0.5 }, { pitch: "C#4", duration: 1.0 },
446  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
447  { pitch: "F4", duration: 2.0 }, // Pure D minor 3rd (F4) - dark, brooding crypt cadence!
448];
449
450const BASE_V2_LEGATO: Note[] = [
451  // Bars 1-4: Legato Soprano Accompaniment from start
452  { pitch: "A4", duration: 1.0 }, { pitch: "D5", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
453  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
454  { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "D5", duration: 1.0 },
455  { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 1.0 },
456  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
457  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
458  { pitch: "D5", duration: 1.0 }, { pitch: "Bb4", duration: 0.5 }, { pitch: "D5", duration: 0.5 },
459  { pitch: "C#5", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "C#5", duration: 0.5 },
460
461  // Bars 5-8: Answer in A minor
462  { pitch: "A4", duration: 1.0 }, { pitch: "C5", duration: 0.5 }, { pitch: "E5", duration: 0.5 },
463  { pitch: "A5", duration: 1.0 }, { pitch: "E5", duration: 0.5 }, { pitch: "C5", duration: 0.5 },
464  { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
465  { pitch: "G4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
466  { pitch: "D4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
467  { pitch: "D5", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
468  { pitch: "G4", duration: 1.0 }, { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
469  { pitch: "E4", duration: 1.0 }, { pitch: "A4", duration: 1.0 },
470
471  // Bars 9-12
472  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "D5", duration: 1.0 },
473  { pitch: "F4", duration: 1.0 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
474  { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "D5", duration: 1.0 },
475  { pitch: "E4", duration: 1.0 }, { pitch: "C#5", duration: 1.0 },
476  { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
477  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
478  { pitch: "Bb4", duration: 1.0 }, { pitch: "D5", duration: 0.5 }, { pitch: "Bb4", duration: 0.5 },
479  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
480
481  // Bars 13-16
482  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
483  { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 },
484  { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
485  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
486  { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
487  { pitch: "Bb4", duration: 1.0 },
488  { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
489  { pitch: "E4", duration: 1.0 },
490  { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
491  { pitch: "F4", duration: 1.0 },
492  { pitch: "E4", duration: 0.5 }, { pitch: "C4", duration: 0.5 },
493  { pitch: "E4", duration: 1.0 },
494  { pitch: "Bb4", duration: 1.0 }, { pitch: "D5", duration: 0.5 }, { pitch: "Bb4", duration: 0.5 },
495  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
496
497  // Bars 17-20
498  { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "C5", duration: 1.0 },
499  { pitch: "E4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "E4", duration: 1.0 },
500  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
501  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
502  { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "Bb4", duration: 1.0 },
503  { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
504  { pitch: "D4", duration: 0.5 }, { pitch: "B3", duration: 0.5 }, { pitch: "D4", duration: 1.0 },
505  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
506
507  // Bars 21-24
508  { pitch: "A4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
509  { pitch: "C5", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
510  { pitch: "Bb4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
511  { pitch: "D5", duration: 1.0 }, { pitch: "Bb4", duration: 0.5 }, { pitch: "F4", duration: 0.5 },
512  { pitch: "D4", duration: 1.0 }, { pitch: "B3", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
513  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
514  { pitch: "C#5", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
515  { pitch: "A4", duration: 1.0 }, { pitch: "E4", duration: 0.5 }, { pitch: "C#4", duration: 0.5 },
516
517  // Bars 25-28
518  { pitch: "A4", duration: 1.0 }, { pitch: "F5", duration: 0.5 }, { pitch: "D5", duration: 0.5 },
519  { pitch: "A4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
520  { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 }, { pitch: "F4", duration: 1.0 },
521  { pitch: "A4", duration: 0.5 }, { pitch: "C5", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
522  { pitch: "Bb4", duration: 0.5 }, { pitch: "G4", duration: 0.5 }, { pitch: "D5", duration: 1.0 },
523  { pitch: "F4", duration: 0.5 }, { pitch: "D5", duration: 0.5 }, { pitch: "Bb4", duration: 1.0 },
524  { pitch: "D4", duration: 1.0 }, { pitch: "B3", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
525  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
526
527  // Bars 29-32
528  { pitch: "Bb4", duration: 1.0 }, { pitch: "G4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
529  { pitch: "A4", duration: 1.0 }, { pitch: "F4", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
530  { pitch: "D4", duration: 1.0 }, { pitch: "B3", duration: 0.5 }, { pitch: "D4", duration: 0.5 },
531  { pitch: "C#4", duration: 1.0 }, { pitch: "E4", duration: 1.0 },
532  { pitch: "C#5", duration: 1.0 }, { pitch: "A4", duration: 0.5 }, { pitch: "E4", duration: 0.5 },
533  { pitch: "C#5", duration: 0.5 }, { pitch: "E5", duration: 0.5 }, { pitch: "A4", duration: 1.0 },
534  { pitch: "D5", duration: 0.5 }, { pitch: "A4", duration: 0.5 }, { pitch: "F4", duration: 0.5 }, { pitch: "A4", duration: 0.5 },
535  { pitch: "D5", duration: 2.0 }, // Pure tonic octave D5 (D minor)
536];
537
538const BASE_V3_LEGATO: Note[] = [
539  // Bars 1-4: Legato Bass Accompaniment from start
540  { pitch: "D2", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 1.0 },
541  { pitch: "D3", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
542  { pitch: "D2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 1.0 },
543  { pitch: "E2", duration: 0.5 }, { pitch: "G2", duration: 0.5 }, { pitch: "C3", duration: 1.0 },
544  { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "D3", duration: 1.0 },
545  { pitch: "D2", duration: 1.0 }, { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
546  { pitch: "G2", duration: 1.0 }, { pitch: "Bb2", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
547  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
548
549  // Bars 5-8: Legato A minor support
550  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
551  { pitch: "A2", duration: 1.0 }, { pitch: "E3", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
552  { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "C3", duration: 1.0 },
553  { pitch: "G2", duration: 1.0 }, { pitch: "A2", duration: 1.0 },
554  { pitch: "D2", duration: 1.0 }, { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
555  { pitch: "D3", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
556  { pitch: "G2", duration: 1.0 }, { pitch: "Bb2", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
557  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
558
559  // Bars 9-12
560  { pitch: "D3", duration: 1.0 }, { pitch: "F3", duration: 0.5 }, { pitch: "A3", duration: 0.5 },
561  { pitch: "D3", duration: 1.0 }, { pitch: "A2", duration: 1.0 },
562  { pitch: "G2", duration: 1.0 }, { pitch: "Bb2", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
563  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
564  { pitch: "F2", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
565  { pitch: "Bb2", duration: 1.0 }, { pitch: "D3", duration: 0.5 }, { pitch: "Bb2", duration: 0.5 },
566  { pitch: "G2", duration: 1.0 }, { pitch: "Bb2", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
567  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
568
569  // Bars 13-16
570  { pitch: "D3", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
571  { pitch: "G2", duration: 0.5 }, { pitch: "D3", duration: 0.5 },
572  { pitch: "C3", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
573  { pitch: "F2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
574  { pitch: "Bb2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
575  { pitch: "G2", duration: 0.5 }, { pitch: "D3", duration: 0.5 },
576  { pitch: "C3", duration: 1.0 },
577  { pitch: "G2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
578  { pitch: "F2", duration: 1.0 },
579  { pitch: "A2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
580  { pitch: "A2", duration: 1.0 },
581  { pitch: "C3", duration: 0.5 }, { pitch: "G2", duration: 0.5 },
582  { pitch: "G2", duration: 0.5 }, { pitch: "Bb2", duration: 0.5 },
583  { pitch: "G2", duration: 1.0 },
584  { pitch: "A2", duration: 1.0 },
585  { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
586
587  // Bars 17-20
588  { pitch: "F3", duration: 1.0 }, { pitch: "C3", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
589  { pitch: "C3", duration: 1.0 }, { pitch: "G2", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
590  { pitch: "D3", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
591  { pitch: "Bb2", duration: 1.0 }, { pitch: "F2", duration: 0.5 }, { pitch: "D2", duration: 0.5 },
592  { pitch: "G2", duration: 1.0 }, { pitch: "D3", duration: 0.5 }, { pitch: "Bb2", duration: 0.5 },
593  { pitch: "D3", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 0.5 },
594  { pitch: "E2", duration: 1.0 }, { pitch: "G2", duration: 0.5 }, { pitch: "E2", duration: 0.5 },
595  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
596
597  // Bars 21-24
598  { pitch: "D3", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 1.0 },
599  { pitch: "F3", duration: 0.5 }, { pitch: "C3", duration: 0.5 }, { pitch: "A2", duration: 1.0 },
600  { pitch: "G2", duration: 0.5 }, { pitch: "D3", duration: 0.5 }, { pitch: "Bb2", duration: 1.0 },
601  { pitch: "Bb2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "D3", duration: 1.0 },
602  { pitch: "E2", duration: 0.5 }, { pitch: "G2", duration: 0.5 }, { pitch: "E2", duration: 1.0 },
603  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
604  { pitch: "A2", duration: 0.5 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 1.0 },
605  { pitch: "A1", duration: 0.5 }, { pitch: "E2", duration: 0.5 }, { pitch: "A1", duration: 1.0 },
606
607  // Bars 25-28
608  { pitch: "D2", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "D3", duration: 1.0 },
609  { pitch: "D2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 1.0 },
610  { pitch: "D2", duration: 1.0 }, { pitch: "F2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
611  { pitch: "F2", duration: 1.0 }, { pitch: "A2", duration: 0.5 }, { pitch: "C3", duration: 0.5 },
612  { pitch: "G2", duration: 1.0 }, { pitch: "D3", duration: 0.5 }, { pitch: "Bb2", duration: 0.5 },
613  { pitch: "Bb2", duration: 1.0 }, { pitch: "F2", duration: 0.5 }, { pitch: "D2", duration: 0.5 },
614  { pitch: "E2", duration: 0.5 }, { pitch: "G2", duration: 0.5 }, { pitch: "E2", duration: 1.0 },
615  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
616
617  // Bars 29-32
618  { pitch: "G2", duration: 0.5 }, { pitch: "D3", duration: 0.5 }, { pitch: "Bb2", duration: 1.0 },
619  { pitch: "D3", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 1.0 },
620  { pitch: "E2", duration: 0.5 }, { pitch: "G2", duration: 0.5 }, { pitch: "E2", duration: 1.0 },
621  { pitch: "A2", duration: 1.0 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 0.5 },
622  { pitch: "A2", duration: 0.5 }, { pitch: "E2", duration: 0.5 }, { pitch: "A2", duration: 1.0 },
623  { pitch: "A2", duration: 0.5 }, { pitch: "C#3", duration: 0.5 }, { pitch: "E3", duration: 1.0 },
624  { pitch: "D2", duration: 0.5 }, { pitch: "A2", duration: 0.5 }, { pitch: "F2", duration: 0.5 }, { pitch: "D2", duration: 0.5 },
625  { pitch: "D2", duration: 2.0 }, // Deep tonic D2 (Pure D minor triad: D2 - F4 - D5)
626];
627
628// Complete Pitch / MIDI Mapping
629const MIDI_TO_NOTE_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
630const MIDI_TO_NOTE_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
631
632const NOTE_TO_MIDI: Record<string, number> = {
633  "C1": 24, "C#1": 25, "Db1": 25, "D1": 26, "D#1": 27, "Eb1": 27, "E1": 28, "F1": 29, "F#1": 30, "Gb1": 30, "G1": 31, "G#1": 32, "Ab1": 32, "A1": 33, "A#1": 34, "Bb1": 34, "B1": 35,
634  "C2": 36, "C#2": 37, "Db2": 37, "D2": 38, "D#2": 39, "Eb2": 39, "E2": 40, "F2": 41, "F#2": 42, "Gb2": 42, "G2": 43, "G#2": 44, "Ab2": 44, "A2": 45, "A#2": 46, "Bb2": 46, "B2": 47,
635  "C3": 48, "C#3": 49, "Db3": 49, "D3": 50, "D#3": 51, "Eb3": 51, "E3": 52, "F3": 53, "F#3": 54, "Gb3": 54, "G3": 55, "G#3": 56, "Ab3": 56, "A3": 57, "A#3": 58, "Bb3": 58, "B3": 59,
636  "C4": 60, "C#4": 61, "Db4": 61, "D4": 62, "D#4": 63, "Eb4": 63, "E4": 64, "F4": 65, "F#4": 66, "Gb4": 66, "G4": 67, "G#4": 68, "Ab4": 68, "A4": 69, "A#4": 70, "Bb4": 70, "B4": 71,
637  "C5": 72, "C#5": 73, "Db5": 73, "D5": 74, "D#5": 75, "Eb5": 75, "E5": 76, "F5": 77, "F#5": 78, "Gb5": 78, "G5": 79, "G#5": 80, "Ab5": 80, "A5": 81, "A#5": 82, "Bb5": 82, "B5": 83,
638  "C6": 84, "C#6": 85, "Db6": 85, "D6": 86, "D#6": 87, "Eb6": 87, "E6": 88, "F6": 89,
639};
640
641function transposePitch(pitch: string, semitones: number, preferFlats: boolean): string {
642  if (pitch === "R") return "R";
643  const midi = NOTE_TO_MIDI[pitch];
644  if (midi === undefined) return pitch;
645  const newMidi = midi + semitones;
646  const octave = Math.floor(newMidi / 12) - 1;
647  const noteIdx = ((newMidi % 12) + 12) % 12;
648  const name = preferFlats ? MIDI_TO_NOTE_FLAT[noteIdx] : MIDI_TO_NOTE_SHARP[noteIdx];
649  return `${name}${octave}`;
650}
651
652function transposeNotes(notes: Note[], semitones: number, preferFlats: boolean): Note[] {
653  return notes.map((n) => ({
654    pitch: transposePitch(n.pitch, semitones, preferFlats),
655    duration: n.duration,
656    staccato: false, // Strict: all staccato removed, keep legato only!
657  }));
658}
659
660function transposeChordTimeline(
661  timeline: { startBeat: number; endBeat: number; chord: string; isDominant?: boolean; isSept?: boolean }[],
662  keyOffset: string,
663  dominantChord: string,
664  minorTonicChord: string
665) {
666  return timeline.map((c) => {
667    let name = c.chord;
668    if (c.isDominant) name = `${dominantChord} (Dominant V resolved)`;
669    else if (c.isSept) name = `Sept chord → resolves to ${dominantChord}`;
670    else if (c.chord.includes("Dark Tonic Cadence")) name = `${minorTonicChord} (Dark Minor Tonic Cadence)`;
671    else name = `${name} [${keyOffset}]`;
672    return { ...c, chord: name };
673  });
674}
675
676// Staccato Theme vs Legato Accompaniment F minor fugue generator
677const FM_STACCATO_THEME_VOICES = (() => {
678  const baseFmV1 = transposeNotes(BASE_V1_LEGATO, 3, true);
679  const baseFmV2 = transposeNotes(BASE_V2_LEGATO, 3, true);
680  const baseFmV3 = transposeNotes(BASE_V3_LEGATO, 3, true);
681
682  // Apply staccato articulation to the Fugue Subject entries in V1, V2, V3
683  const applyStaccatoToSubject = (notes: Note[], subjectStartBeats: number[]) => {
684    let curBeat = 0;
685    return notes.map((n) => {
686      const noteStart = curBeat;
687      curBeat += n.duration;
688      // Check if this note is inside a subject entry phrase (4 measures = 16 beats)
689      const isSubjectNote = subjectStartBeats.some(
690        (start) => noteStart >= start && noteStart < start + 16
691      );
692      return {
693        ...n,
694        staccato: isSubjectNote ? true : false,
695      };
696    });
697  };
698
699  return {
700    v1: applyStaccatoToSubject(baseFmV1, [0, 16, 64, 96]), // Bars 1-4, 5-8, 17-20, 25-28
701    v2: applyStaccatoToSubject(baseFmV2, [16, 96]), // Bars 5-8, 25-28
702    v3: applyStaccatoToSubject(baseFmV3, [32, 96]), // Bars 9-12, 25-28
703  };
704})();
705
706// ---------------------------------------------------------
707// 6 DISTINCT CONTRASTING THEME VARIATIONS (ALL 32 BARS COMPLETE)
708// 1. D minor (The Crypt Fugue)
709// 2. F minor (Catacomb Lament - requested in prompt)
710// 3. C minor (Dungeon Passacaglia)
711// 4. G minor (Shadow Fantasia)
712// 5. A minor (Sepulcher Ricercar)
713// 6. E minor (Necromancer Toccata)
714// ---------------------------------------------------------
715const THEME_VARIANTS: ThemeVariant[] = [
716  {
717    id: "d_minor_crypt",
718    name: "I. The Crypt Fugue",
719    key: "Dm",
720    keyName: "D minor",
721    subtitle: "D minor • Pure Legato Polyphony",
722    description: "Original solemn Bach fugue in D minor. Singing legato lines, continuous 3-voice accompaniment, dark minor ending.",
723    v1: BASE_V1_LEGATO,
724    v2: BASE_V2_LEGATO,
725    v3: BASE_V3_LEGATO,
726    chords: CHORD_TIMELINE,
727  },
728  {
729    id: "f_minor_lament",
730    name: "II. Catacomb Lament (Legato)",
731    key: "Fm",
732    keyName: "F minor",
733    subtitle: "F minor • Solemn & Tragic Echoes",
734    description: "Deep subterranean F minor counterpoint with pure legato arches and dark F minor resolution.",
735    v1: transposeNotes(BASE_V1_LEGATO, 3, true),
736    v2: transposeNotes(BASE_V2_LEGATO, 3, true),
737    v3: transposeNotes(BASE_V3_LEGATO, 3, true),
738    chords: transposeChordTimeline(CHORD_TIMELINE, "Fm", "C Major", "F minor Triad"),
739  },
740  {
741    id: "f_minor_staccato_theme",
742    name: "IIb. Catacomb Lament (Staccato Theme)",
743    key: "Fm",
744    keyName: "F minor",
745    subtitle: "F minor • Staccato Subject & Legato Accompaniment",
746    description: "F minor fugue with crisp staccato theme subjects contrasted against smooth legato accompaniment.",
747    v1: FM_STACCATO_THEME_VOICES.v1,
748    v2: FM_STACCATO_THEME_VOICES.v2,
749    v3: FM_STACCATO_THEME_VOICES.v3,
750    chords: transposeChordTimeline(CHORD_TIMELINE, "Fm", "C Major", "F minor Triad"),
751  },
752  {
753    id: "c_minor_passacaglia",
754    name: "III. Dungeon Passacaglia",
755    key: "Cm",
756    keyName: "C minor",
757    subtitle: "C minor • Ground-Bass Majesty",
758    description: "In the noble key of the Bach Passacaglia. Seamless legato counterpoint resolving to dark C minor.",
759    v1: transposeNotes(BASE_V1_LEGATO, -2, true),
760    v2: transposeNotes(BASE_V2_LEGATO, -2, true),
761    v3: transposeNotes(BASE_V3_LEGATO, -2, true),
762    chords: transposeChordTimeline(CHORD_TIMELINE, "Cm", "G Major", "C minor Triad"),
763  },
764  {
765    id: "g_minor_fantasia",
766    name: "IV. Shadow Fantasia",
767    key: "Gm",
768    keyName: "G minor",
769    subtitle: "G minor • Noble Baroque Elegance",
770    description: "Haunting G minor modal dialogue. Rich 3-channel legato textures resolving to dark G minor.",
771    v1: transposeNotes(BASE_V1_LEGATO, 5, true),
772    v2: transposeNotes(BASE_V2_LEGATO, 5, true),
773    v3: transposeNotes(BASE_V3_LEGATO, 5, true),
774    chords: transposeChordTimeline(CHORD_TIMELINE, "Gm", "D Major", "G minor Triad"),
775  },
776  {
777    id: "a_minor_ricercar",
778    name: "V. Sepulcher Ricercar",
779    key: "Am",
780    keyName: "A minor",
781    subtitle: "A minor • Contrapuntal Purity",
782    description: "Modal clarity and singing organ lines in A minor, resolving to dark A minor.",
783    v1: transposeNotes(BASE_V1_LEGATO, 7, false),
784    v2: transposeNotes(BASE_V2_LEGATO, 7, false),
785    v3: transposeNotes(BASE_V3_LEGATO, 7, false),
786    chords: transposeChordTimeline(CHORD_TIMELINE, "Am", "E Major", "A minor Triad"),
787  },
788  {
789    id: "e_minor_toccata",
790    name: "VI. Necromancer Toccata",
791    key: "Em",
792    keyName: "E minor",
793    subtitle: "E minor • Cathedral Crypt Drive",
794    description: "Driving 74 BPM Baroque polyphony in E minor ('The Wedge'), resolving to dark E minor.",
795    v1: transposeNotes(BASE_V1_LEGATO, 2, false),
796    v2: transposeNotes(BASE_V2_LEGATO, 2, false),
797    v3: transposeNotes(BASE_V3_LEGATO, 2, false),
798    chords: transposeChordTimeline(CHORD_TIMELINE, "Em", "B Major", "E minor Triad"),
799  },
800];
801
802function getFreq(pitch: string): number {
803  if (pitch === "R" || !NOTE_TO_MIDI[pitch]) return 0;
804  const midi = NOTE_TO_MIDI[pitch];
805  return 440 * Math.pow(2, (midi - 69) / 12);
806}
807
808// AY-3-8912 logarithmic 16-step DAC volume curve (levels 0-15)
809const AY_VOL_TABLE = [
810  0.0, 0.007, 0.011, 0.016, 0.024, 0.035, 0.051, 0.075,
811  0.110, 0.160, 0.235, 0.345, 0.505, 0.740, 0.880, 1.0,
812];
813
814// Color palette for ZX Spectrum 128k
815const SPECTRUM_BORDER_COLORS = [
816  { name: "0: BLACK", hex: "#000000" },
817  { name: "1: BLUE", hex: "#0000D7" },
818  { name: "2: RED", hex: "#D70000" },
819  { name: "3: MAGENTA", hex: "#D700D7" },
820  { name: "4: GREEN", hex: "#00D700" },
821  { name: "5: CYAN", hex: "#00D7D7" },
822  { name: "6: YELLOW", hex: "#D7D700" },
823  { name: "7: WHITE", hex: "#D7D7D7" },
824];
825
826export default function Component() {
827  const [isPlaying, setIsPlaying] = useState(false);
828  const [bpm, setBpm] = useState(74); // Default 74 BPM as requested
829  const [currentBeat, setCurrentBeat] = useState(0);
830  const [masterVolume, setMasterVolume] = useState(0.85);
831  const [reverbMix, setReverbMix] = useState(0.5); // Gothic organ reverb mix (0 to 1)
832
833  // Active Variation State & Game Cues State
834  const [playbackMode, setPlaybackMode] = useState<"FUGUE" | "CUE">("FUGUE");
835  const [selectedCueId, setSelectedCueId] = useState<GameCue["id"]>("dungeon_crawl");
836  const [cuePlayMode, setCuePlayMode] = useState<"LOOP_SINGLE" | "CHAIN_STORY">("LOOP_SINGLE");
837  const [nextQueuedCueId, setNextQueuedCueId] = useState<GameCue["id"] | null>(null);
838
839  const [selectedVariantId, setSelectedVariantId] = useState<ThemeVariant["id"]>("d_minor_crypt");
840
841  const activeCue = useMemo(() => {
842    return GAME_CUES.find((c) => c.id === selectedCueId) || GAME_CUES[0];
843  }, [selectedCueId]);
844
845  const activeVariant = useMemo(() => {
846    return THEME_VARIANTS.find((v) => v.id === selectedVariantId) || THEME_VARIANTS[0];
847  }, [selectedVariantId]);
848
849  // Audio settings
850  const [panningMode, setPanningMode] = useState<"ACB" | "ABC" | "MONO">("ACB");
851  const [soundMode, setSoundMode] = useState<"AY_PURE" | "CRYPT_ORGAN" | "HARPSICHORD">("CRYPT_ORGAN");
852  const [channelMutes, setChannelMutes] = useState({ A: false, B: false, C: false });
853  const [channelSolos, setChannelSolos] = useState({ A: false, B: false, C: false });
854  const [borderColorIdx, setBorderColorIdx] = useState(0);
855
856  // Audio Context & Nodes refs
857  const audioCtxRef = useRef<AudioContext | null>(null);
858  const masterGainRef = useRef<GainNode | null>(null);
859  const filterNodeRef = useRef<BiquadFilterNode | null>(null);
860  const convolverRef = useRef<ConvolverNode | null>(null);
861  const dryGainRef = useRef<GainNode | null>(null);
862  const wetGainRef = useRef<GainNode | null>(null);
863
864  // Voice channels refs
865  const channelNodesRef = useRef<{
866    A?: { osc: OscillatorNode; gain: GainNode; pan: StereoPannerNode };
867    B?: { osc: OscillatorNode; gain: GainNode; pan: StereoPannerNode };
868    C?: { osc: OscillatorNode; gain: GainNode; pan: StereoPannerNode };
869  }>({});
870
871  // Active note trackers for UI
872  const [activeNotes, setActiveNotes] = useState<{ A: string; B: string; C: string }>({ A: "-", B: "-", C: "-" });
873  const [activeLevels, setActiveLevels] = useState<{ A: number; B: number; C: number }>({ A: 0, B: 0, C: 0 });
874
875  // Playback scheduler refs
876  const isPlayingRef = useRef(false);
877  isPlayingRef.current = isPlaying;
878  const currentBeatRef = useRef(0);
879  const bpmRef = useRef(bpm);
880  bpmRef.current = bpm;
881  const masterVolumeRef = useRef(masterVolume);
882  masterVolumeRef.current = masterVolume;
883  const soundModeRef = useRef(soundMode);
884  soundModeRef.current = soundMode;
885  const channelMutesRef = useRef(channelMutes);
886  channelMutesRef.current = channelMutes;
887  const channelSolosRef = useRef(channelSolos);
888  channelSolosRef.current = channelSolos;
889
890  const animFrameRef = useRef<number | null>(null);
891  const lastTimeRef = useRef<number>(0);
892
893  // Export / Code inspection modal state
894  const [showExportModal, setShowExportModal] = useState(false);
895  const [exportTab, setExportTab] = useState<"INDIVIDUAL" | "VIEWER">("INDIVIDUAL");
896  const [exportFormat, setExportFormat] = useState<"ABC" | "PT3" | "JSON">("ABC");
897  const [exportScope, setExportScope] = useState<"CURRENT" | "ALL">("CURRENT");
898  const [copiedCode, setCopiedCode] = useState(false);
899
900  // Precompute beat offsets for each voice note dynamically per selected Theme Variant
901  const voiceSchedules = useMemo(() => {
902    const buildTimeline = (notes: Note[]) => {
903      let time = 0;
904      return notes.map((n) => {
905        const item = { ...n, startBeat: time, endBeat: time + n.duration };
906        time += n.duration;
907        return item;
908      });
909    };
910    if (playbackMode === "CUE") {
911      return {
912        A: buildTimeline(activeCue.v1),
913        B: buildTimeline(activeCue.v2),
914        C: buildTimeline(activeCue.v3),
915        totalBeats: activeCue.totalBeats,
916        loop: activeCue.loop,
917      };
918    }
919    return {
920      A: buildTimeline(activeVariant.v1),
921      B: buildTimeline(activeVariant.v2),
922      C: buildTimeline(activeVariant.v3),
923      totalBeats: 128,
924      loop: true,
925    };
926  }, [playbackMode, activeCue, activeVariant]);
927
928  // Initialize Web Audio Engine
929  const initAudio = useCallback(() => {
930    if (audioCtxRef.current) return audioCtxRef.current;
931
932    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
933    audioCtxRef.current = ctx;
934
935    const masterGain = ctx.createGain();
936    masterGain.gain.setValueAtTime(masterVolumeRef.current, ctx.currentTime);
937    masterGainRef.current = masterGain;
938
939    // Authentic Spectrum 128k TV Speaker Filter (Warm lowpass around 6.5kHz)
940    const filter = ctx.createBiquadFilter();
941    filter.type = "lowpass";
942    filter.frequency.setValueAtTime(6800, ctx.currentTime);
943    filter.Q.setValueAtTime(0.7, ctx.currentTime);
944    filterNodeRef.current = filter;
945
946    // Optional crypt reverb convolution for "Cathedral Crypt Organ" mode
947    const conv = ctx.createConvolver();
948    // Synthesize procedural Gothic crypt impulse response
949    const rate = ctx.sampleRate;
950    const length = rate * 2.8; // 2.8 seconds crypt decay
951    const decayBuffer = ctx.createBuffer(2, length, rate);
952    for (let c = 0; c < 2; c++) {
953      const channelData = decayBuffer.getChannelData(c);
954      for (let i = 0; i < length; i++) {
955        const t = i / rate;
956        // Exponential decay with slight early reflections
957        const env = Math.exp(-t * 2.0);
958        const noise = (Math.random() * 2 - 1) * env;
959        channelData[i] = noise;
960      }
961    }
962    conv.buffer = decayBuffer;
963    convolverRef.current = conv;
964
965    const dryGain = ctx.createGain();
966    const wetGain = ctx.createGain();
967    dryGain.gain.setValueAtTime(1.0, ctx.currentTime);
968    wetGain.gain.setValueAtTime(0.0, ctx.currentTime);
969    dryGainRef.current = dryGain;
970    wetGainRef.current = wetGain;
971
972    // Graph routing
973    filter.connect(dryGain);
974    filter.connect(conv);
975    conv.connect(wetGain);
976
977    dryGain.connect(masterGain);
978    wetGain.connect(masterGain);
979    masterGain.connect(ctx.destination);
980
981    // Create 3 AY-3-8912 channels: A, B, C
982    const channels: ("A" | "B" | "C")[] = ["A", "B", "C"];
983    const nodes: typeof channelNodesRef.current = {};
984
985    channels.forEach((ch) => {
986      const osc = ctx.createOscillator();
987      osc.type = "square"; // AY-3-8912 is pure square wave!
988      osc.frequency.setValueAtTime(440, ctx.currentTime);
989
990      const gain = ctx.createGain();
991      gain.gain.setValueAtTime(0, ctx.currentTime);
992
993      const pan = ctx.createStereoPanner();
994      pan.pan.setValueAtTime(0, ctx.currentTime);
995
996      osc.connect(gain);
997      gain.connect(pan);
998      pan.connect(filter);
999
1000      osc.start();
1001      nodes[ch] = { osc, gain, pan };
1002    });
1003
1004    channelNodesRef.current = nodes;
1005    return ctx;
1006  }, []);
1007
1008  // Update panning according to ZX Spectrum standard layout (Stereo ACB is standard on ZX 128k)
1009  useEffect(() => {
1010    const nodes = channelNodesRef.current;
1011    if (!nodes.A || !nodes.B || !nodes.C) return;
1012    const ctx = audioCtxRef.current;
1013    if (!ctx) return;
1014
1015    if (panningMode === "ACB") {
1016      // Channel A (Left -0.8), Channel C (Center 0.0), Channel B (Right +0.8)
1017      nodes.A.pan.pan.setValueAtTime(-0.75, ctx.currentTime);
1018      nodes.C.pan.pan.setValueAtTime(0.0, ctx.currentTime);
1019      nodes.B.pan.pan.setValueAtTime(0.75, ctx.currentTime);
1020    } else if (panningMode === "ABC") {
1021      // Channel A (Left -0.8), Channel B (Center 0.0), Channel C (Right +0.8)
1022      nodes.A.pan.pan.setValueAtTime(-0.75, ctx.currentTime);
1023      nodes.B.pan.pan.setValueAtTime(0.0, ctx.currentTime);
1024      nodes.C.pan.pan.setValueAtTime(0.75, ctx.currentTime);
1025    } else {
1026      // Mono
1027      nodes.A.pan.pan.setValueAtTime(0.0, ctx.currentTime);
1028      nodes.B.pan.pan.setValueAtTime(0.0, ctx.currentTime);
1029      nodes.C.pan.pan.setValueAtTime(0.0, ctx.currentTime);
1030    }
1031  }, [panningMode]);
1032
1033  // Update sound mode characteristics (AY Pure, Crypt Organ, Harpsichord)
1034  useEffect(() => {
1035    const ctx = audioCtxRef.current;
1036    if (!ctx || !dryGainRef.current || !wetGainRef.current || !filterNodeRef.current) return;
1037    const nodes = channelNodesRef.current;
1038
1039    if (soundMode === "CRYPT_ORGAN") {
1040      // Add cathedral hall reverberation
1041      dryGainRef.current.gain.setTargetAtTime(0.75, ctx.currentTime, 0.05);
1042      wetGainRef.current.gain.setTargetAtTime(0.45, ctx.currentTime, 0.05);
1043      filterNodeRef.current.frequency.setTargetAtTime(8000, ctx.currentTime, 0.05);
1044      if (nodes.A && nodes.B && nodes.C) {
1045        nodes.A.osc.type = "sawtooth";
1046        nodes.B.osc.type = "square";
1047        nodes.C.osc.type = "triangle";
1048      }
1049    } else if (soundMode === "HARPSICHORD") {
1050      dryGainRef.current.gain.setTargetAtTime(0.9, ctx.currentTime, 0.05);
1051      wetGainRef.current.gain.setTargetAtTime(0.15, ctx.currentTime, 0.05);
1052      filterNodeRef.current.frequency.setTargetAtTime(9500, ctx.currentTime, 0.05);
1053      if (nodes.A && nodes.B && nodes.C) {
1054        nodes.A.osc.type = "sawtooth";
1055        nodes.B.osc.type = "sawtooth";
1056        nodes.C.osc.type = "sawtooth";
1057      }
1058    } else {
1059      // Pure AY-3-8912 Chiptune Square Wave
1060      dryGainRef.current.gain.setTargetAtTime(1.0, ctx.currentTime, 0.05);
1061      wetGainRef.current.gain.setTargetAtTime(0.0, ctx.currentTime, 0.05);
1062      filterNodeRef.current.frequency.setTargetAtTime(6500, ctx.currentTime, 0.05);
1063      if (nodes.A && nodes.B && nodes.C) {
1064        nodes.A.osc.type = "square";
1065        nodes.B.osc.type = "square";
1066        nodes.C.osc.type = "square";
1067      }
1068    }
1069  }, [soundMode]);
1070
1071  // Dynamic Reverb Mix Update
1072  useEffect(() => {
1073    const ctx = audioCtxRef.current;
1074    if (!ctx || !dryGainRef.current || !wetGainRef.current) return;
1075    
1076    if (soundMode === "AY_PURE") {
1077      dryGainRef.current.gain.setTargetAtTime(1.0, ctx.currentTime, 0.02);
1078      wetGainRef.current.gain.setTargetAtTime(0.0, ctx.currentTime, 0.02);
1079    } else {
1080      const wet = reverbMix;
1081      const dry = Math.max(0.3, 1.0 - wet * 0.5);
1082      dryGainRef.current.gain.setTargetAtTime(dry, ctx.currentTime, 0.02);
1083      wetGainRef.current.gain.setTargetAtTime(wet, ctx.currentTime, 0.02);
1084    }
1085  }, [reverbMix, soundMode]);
1086
1087  // Find active note in voice for given beat
1088  const getNoteAtBeat = useCallback((notes: (Note & { startBeat: number; endBeat: number })[], beat: number) => {
1089    for (let i = 0; i < notes.length; i++) {
1090      if (beat >= notes[i].startBeat && beat < notes[i].endBeat) {
1091        return notes[i];
1092      }
1093    }
1094    return null;
1095  }, []);
1096
1097  // Main playback tick loop using high precision AudioContext timing
1098  useEffect(() => {
1099    if (!isPlaying) {
1100      // Mute audio outputs when paused
1101      if (channelNodesRef.current) {
1102        const ctx = audioCtxRef.current;
1103        if (ctx) {
1104          Object.values(channelNodesRef.current).forEach((ch) => {
1105            if (ch?.gain) ch.gain.gain.setValueAtTime(0, ctx.currentTime);
1106          });
1107        }
1108      }
1109      return;
1110    }
1111
1112    const ctx = initAudio();
1113    if (ctx.state === "suspended") {
1114      ctx.resume();
1115    }
1116
1117    lastTimeRef.current = performance.now();
1118
1119    const loop = (now: number) => {
1120      if (!isPlayingRef.current) return;
1121
1122      const deltaSec = (now - lastTimeRef.current) / 1000;
1123      lastTimeRef.current = now;
1124
1125      const beatsPerSec = bpmRef.current / 60;
1126      let newBeat = currentBeatRef.current + deltaSec * beatsPerSec;
1127
1128      const totalBeats = voiceSchedules.totalBeats;
1129
1130      if (newBeat >= totalBeats) {
1131        if (playbackMode === "CUE") {
1132          if (cuePlayMode === "CHAIN_STORY") {
1133            // Automatically advance to the next story cue in the dungeon progression
1134            const storyProgression: Record<GameCue["id"], GameCue["id"]> = {
1135              dungeon_crawl: "dangerous",
1136              dangerous: "boss_fight",
1137              boss_fight: "level_complete",
1138              level_complete: "game_win",
1139              game_win: "dungeon_crawl",
1140              game_over: "dungeon_crawl",
1141            };
1142            const nextId = nextQueuedCueId || storyProgression[selectedCueId];
1143            setNextQueuedCueId(null);
1144            setSelectedCueId(nextId);
1145            newBeat = 0;
1146          } else if (nextQueuedCueId) {
1147            // User queued another cue to transition into seamlessly at phrase boundary
1148            setSelectedCueId(nextQueuedCueId);
1149            setNextQueuedCueId(null);
1150            newBeat = 0;
1151          } else {
1152            // Infinite seamless loop of current cue
1153            newBeat = newBeat % totalBeats;
1154          }
1155        } else {
1156          // Fugue loop
1157          newBeat = newBeat % totalBeats;
1158        }
1159      }
1160      currentBeatRef.current = newBeat;
1161      setCurrentBeat(newBeat);
1162
1163      // Check which channels are audible based on Solo / Mute
1164      const hasAnySolo = channelSolosRef.current.A || channelSolosRef.current.B || channelSolosRef.current.C;
1165      const isAudible = (ch: "A" | "B" | "C") => {
1166        if (hasAnySolo) return channelSolosRef.current[ch];
1167        return !channelMutesRef.current[ch];
1168      };
1169
1170      const nodes = channelNodesRef.current;
1171      const currentTime = ctx.currentTime;
1172
1173      // Update Channel A (Alto / Voice 1)
1174      const noteA = getNoteAtBeat(voiceSchedules.A, newBeat);
1175      const noteB = getNoteAtBeat(voiceSchedules.B, newBeat);
1176      const noteC = getNoteAtBeat(voiceSchedules.C, newBeat);
1177
1178      const applyVoice = (
1179        ch: "A" | "B" | "C",
1180        noteItem: (Note & { startBeat: number; endBeat: number }) | null,
1181        baseVolLevel: number
1182      ) => {
1183        const node = nodes[ch];
1184        if (!node) return { pitch: "-", level: 0 };
1185
1186        if (!noteItem || noteItem.pitch === "R" || !isAudible(ch)) {
1187          node.gain.gain.setTargetAtTime(0, currentTime, 0.005);
1188          return { pitch: "-", level: 0 };
1189        }
1190
1191        const freq = getFreq(noteItem.pitch);
1192        if (freq > 0) {
1193          // Pure legato portamento transition between adjacent counterpoint notes
1194          node.osc.frequency.setTargetAtTime(freq, currentTime, 0.006);
1195        }
1196
1197        // Apply staccato envelope if specified on note, otherwise keep pure legato sustain
1198        let levelIndex = baseVolLevel;
1199        if (noteItem.staccato) {
1200          const noteProgress = (newBeat - noteItem.startBeat) / noteItem.duration;
1201          if (noteProgress > 0.45) {
1202            levelIndex = 0; // Short staccato cut for classic AY walking bass/counterpoint
1203          }
1204        }
1205
1206        const targetGain = AY_VOL_TABLE[levelIndex] * 0.28;
1207        node.gain.gain.setTargetAtTime(targetGain, currentTime, 0.006);
1208
1209        return { pitch: noteItem.pitch, level: levelIndex };
1210      };
1211
1212      const resA = applyVoice("A", noteA, 13);
1213      const resB = applyVoice("B", noteB, 13);
1214      const resC = applyVoice("C", noteC, 14); // Bass gets slightly higher AY volume weight
1215
1216      setActiveNotes({ A: resA.pitch, B: resB.pitch, C: resC.pitch });
1217      setActiveLevels({ A: resA.level, B: resB.level, C: resC.level });
1218
1219      animFrameRef.current = requestAnimationFrame(loop);
1220    };
1221
1222    animFrameRef.current = requestAnimationFrame(loop);
1223
1224    return () => {
1225      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
1226    };
1227  }, [isPlaying, getNoteAtBeat, initAudio, voiceSchedules]);
1228
1229  // Current bar and section
1230  const currentBar = Math.floor(currentBeat / 4) + 1;
1231  const currentSection = useMemo(() => {
1232    if (playbackMode === "CUE") {
1233      return {
1234        name: `OST Cue: ${activeCue.name} (F minor)`,
1235        description: activeCue.subtitle,
1236      };
1237    }
1238    return (
1239      FUGUE_SECTIONS.find((s) => currentBar >= s.startBar && currentBar <= s.endBar) || FUGUE_SECTIONS[0]
1240    );
1241  }, [currentBar, playbackMode, activeCue]);
1242
1243  const currentChord = useMemo(() => {
1244    const list = playbackMode === "CUE" ? activeCue.chords : activeVariant.chords;
1245    const entry = list.find((c) => currentBeat >= c.startBeat && currentBeat < c.endBeat);
1246    return entry || { chord: "F minor Triad", isDominant: false, isSept: false };
1247  }, [currentBeat, playbackMode, activeCue, activeVariant]);
1248
1249  const playCue = (cueId: GameCue["id"], immediate = false) => {
1250    const cue = GAME_CUES.find((c) => c.id === cueId);
1251    if (!cue) return;
1252    initAudio();
1253
1254    if (playbackMode === "CUE" && isPlaying && !immediate) {
1255      // Quantized transition: Queue to transition seamlessly on the next phrase turnaround!
1256      setNextQueuedCueId(cueId);
1257    } else {
1258      setSelectedCueId(cueId);
1259      setNextQueuedCueId(null);
1260      setPlaybackMode("CUE");
1261      setBpm(cue.defaultBpm);
1262      currentBeatRef.current = 0;
1263      setCurrentBeat(0);
1264      setIsPlaying(true);
1265    }
1266  };
1267
1268  const returnToFugue = () => {
1269    setPlaybackMode("FUGUE");
1270    setBpm(74);
1271    currentBeatRef.current = 0;
1272    setCurrentBeat(0);
1273    setIsPlaying(true);
1274  };
1275
1276  const togglePlay = () => {
1277    initAudio();
1278    setIsPlaying(!isPlaying);
1279  };
1280
1281  const handleRewind = () => {
1282    currentBeatRef.current = 0;
1283    setCurrentBeat(0);
1284  };
1285
1286  const toggleMute = (ch: "A" | "B" | "C") => {
1287    setChannelMutes((prev) => ({ ...prev, [ch]: !prev[ch] }));
1288  };
1289
1290  const toggleSolo = (ch: "A" | "B" | "C") => {
1291    setChannelSolos((prev) => ({ ...prev, [ch]: !prev[ch] }));
1292  };
1293
1294  const cycleBorder = () => {
1295    setBorderColorIdx((prev) => (prev + 1) % SPECTRUM_BORDER_COLORS.length);
1296  };
1297
1298  // Helper to generate ABC 2.1 notation (Dynamic key signature and support for all variants)
1299  const generateABCForVariant = useCallback((variant: ThemeVariant, index = 1) => {
1300    let abc = `%abc-2.1\nX:${index}\nT:Tome of the Dead - ${variant.name} (${variant.keyName})\n`;
1301    abc += `C:ZX Spectrum 128K AY-3-8912 Chiptune\nM:4/4\nL:1/8\nQ:1/4=${bpm}\nK:${variant.key}\n`;
1302    abc += `%%score (V1 V2) V3\n`;
1303
1304    const pitchToABC = (p: string, dur: number, staccato?: boolean) => {
1305      if (p === "R") return `z${Math.round(dur * 2)}`;
1306      const len = Math.max(1, Math.round(dur * 2));
1307      const lenStr = len === 1 ? "" : `${len}`;
1308      const dot = staccato ? "." : "";
1309
1310      const noteMap: Record<string, string> = {
1311        "A1": "A,,", "Bb1": "_B,,", "B1": "B,,",
1312        "C2": "C,", "C#2": "^C,", "Db2": "_D,", "D2": "D,", "D#2": "^D,", "Eb2": "_E,", "E2": "E,", "F2": "F,", "F#2": "^F,", "Gb2": "_G,", "G2": "G,", "G#2": "^G,", "Ab2": "_A,", "A2": "A,", "Bb2": "_B,", "B2": "B,",
1313        "C3": "C", "C#3": "^C", "Db3": "_D", "D3": "D", "D#3": "^D", "Eb3": "_E", "E3": "E", "F3": "F", "F#3": "^F", "Gb3": "_G", "G3": "G", "G#3": "^G", "Ab3": "_A", "A3": "A", "Bb3": "_B", "B3": "B",
1314        "C4": "c", "C#4": "^c", "Db4": "_d", "D4": "d", "D#4": "^d", "Eb4": "_e", "E4": "e", "F4": "f", "F#4": "^f", "Gb4": "_g", "G4": "g", "G#4": "^g", "Ab4": "_a", "A4": "a", "Bb4": "_b", "B4": "b",
1315        "C5": "c'", "C#5": "^c'", "Db5": "_d'", "D5": "d'", "D#5": "^d'", "Eb5": "_e'", "E5": "e'", "F5": "f'", "F#5": "^f'", "Gb5": "_g'", "G5": "g'", "G#5": "^g'", "Ab5": "_a'", "A5": "a'", "Bb5": "_b'", "B5": "b'",
1316        "C6": "c''", "C#6": "^c''", "D6": "d''",
1317      };
1318      const mapped = noteMap[p] || "d";
1319      return `${dot}${mapped}${lenStr}`;
1320    };
1321
1322    const renderVoice = (id: string, notes: Note[], clef: string) => {
1323      let out = `V:${id} clef=${clef} name="${id}"\n`;
1324      let curBeat = 0;
1325      notes.forEach((n) => {
1326        out += pitchToABC(n.pitch, n.duration, n.staccato) + " ";
1327        curBeat += n.duration;
1328        if (Math.abs(curBeat % 4) < 0.01) {
1329          out += "| ";
1330        }
1331        if (Math.abs(curBeat % 16) < 0.01) {
1332          out += "\n";
1333        }
1334      });
1335      out += "\n";
1336      return out;
1337    };
1338
1339    abc += renderVoice("V1", variant.v1, "treble");
1340    abc += renderVoice("V2", variant.v2, "treble");
1341    abc += renderVoice("V3", variant.v3, "bass");
1342    return abc;
1343  }, [bpm]);
1344
1345  // Helper to generate Vortex Tracker II / ProTracker 3 (PT3) for any specific cue
1346  const generateCuePT3 = useCallback((cue: GameCue) => {
1347    let pt3 = `; =========================================================\n`;
1348    pt3 += `; ProTracker 3.xx / Vortex Tracker II Module Source\n`;
1349    pt3 += `; Title: Tome of the Dead - ${cue.name} (F minor)\n`;
1350    pt3 += `; Chip: AY-3-8912 (1.773400 MHz), Stereo ACB / Mono\n`;
1351    pt3 += `; Tempo: ${cue.defaultBpm} BPM (Interrupt: 50 Hz, Speed: 6)\n`;
1352    pt3 += `; Channels: A = Alto, B = Soprano, C = Bass\n`;
1353    pt3 += `; =========================================================\n\n`;
1354    pt3 += `[Module]\nTitle=${cue.name}\nAuthor=Producer\nTempo=${cue.defaultBpm}\nSpeed=6\n\n`;
1355    pt3 += `Pattern 0:\n; Row | Chan A (Alto)    | Chan B (Soprano) | Chan C (Bass)     |\n`;
1356
1357    const getNoteAtTime = (notes: Note[], beat: number) => {
1358      let b = 0;
1359      for (const n of notes) {
1360        if (beat >= b && beat < b + n.duration) return n;
1361        b += n.duration;
1362      }
1363      return null;
1364    };
1365
1366    const fmtNote = (n: Note | null) => {
1367      if (!n || n.pitch === "R") return "... ...";
1368      const p = n.pitch.replace("#", "+").replace("Db", "D-").replace("Ab", "A-").replace("Bb", "B-").replace("Eb", "E-").replace("Gb", "G-").padEnd(3, "-");
1369      return `${p} v14`;
1370    };
1371
1372    const totalRows = Math.round(cue.totalBeats * 2);
1373    for (let r = 0; r < totalRows; r++) {
1374      const curBeat = r * 0.5;
1375      const nA = getNoteAtTime(cue.v1, curBeat);
1376      const nB = getNoteAtTime(cue.v2, curBeat);
1377      const nC = getNoteAtTime(cue.v3, curBeat);
1378      pt3 += `${r.toString().padStart(2, "0")}: | ${fmtNote(nA)} | ${fmtNote(nB)} | ${fmtNote(nC)} |\n`;
1379    }
1380    pt3 += `\n; End of Cue Module\n`;
1381    return pt3;
1382  }, []);
1383
1384  // Helper to generate Vortex Tracker II / ProTracker 3 (PT3) for any specific fugue variant
1385  const generateVariantPT3 = useCallback((variant: ThemeVariant) => {
1386    let pt3 = `; =========================================================\n`;
1387    pt3 += `; ProTracker 3.xx / Vortex Tracker II Module Source\n`;
1388    pt3 += `; Title: Tome of the Dead - ${variant.name} (${variant.keyName})\n`;
1389    pt3 += `; Chip: AY-3-8912 (1.773400 MHz), Stereo ACB / Mono\n`;
1390    pt3 += `; Tempo: ${bpm} BPM (Interrupt: 50 Hz, Speed: 6)\n`;
1391    pt3 += `; Channels: A = Alto, B = Soprano, C = Bass\n`;
1392    pt3 += `; =========================================================\n\n`;
1393    pt3 += `[Module]\nTitle=${variant.name}\nAuthor=Producer\nTempo=${bpm}\nSpeed=6\n\n`;
1394
1395    const getNoteAtTime = (notes: Note[], beat: number) => {
1396      let b = 0;
1397      for (const n of notes) {
1398        if (beat >= b && beat < b + n.duration) return n;
1399        b += n.duration;
1400      }
1401      return null;
1402    };
1403
1404    const fmtNote = (n: Note | null) => {
1405      if (!n || n.pitch === "R") return "... ...";
1406      const p = n.pitch.replace("#", "+").replace("Db", "D-").replace("Ab", "A-").replace("Bb", "B-").replace("Eb", "E-").replace("Gb", "G-").padEnd(3, "-");
1407      const vol = n.staccato ? "v09" : "v14";
1408      return `${p} ${vol}`;
1409    };
1410
1411    for (let pat = 0; pat < 4; pat++) {
1412      pt3 += `Pattern ${pat}:\n; Row | Chan A (Alto)    | Chan B (Soprano) | Chan C (Bass)     |\n`;
1413      for (let r = 0; r < 32; r++) {
1414        const curBeat = (pat * 32 + r) * 0.5;
1415        const nA = getNoteAtTime(variant.v1, curBeat);
1416        const nB = getNoteAtTime(variant.v2, curBeat);
1417        const nC = getNoteAtTime(variant.v3, curBeat);
1418        pt3 += `${r.toString().padStart(2, "0")}: | ${fmtNote(nA)} | ${fmtNote(nB)} | ${fmtNote(nC)} |\n`;
1419      }
1420      pt3 += `\n`;
1421    }
1422    pt3 += `; End of Fugue Module (32 Measures)\n`;
1423    return pt3;
1424  }, [bpm]);
1425
1426  const generateABC = useCallback(() => {
1427    if (exportScope === "ALL") {
1428      return THEME_VARIANTS.map((v, i) => generateABCForVariant(v, i + 1)).join("\n\n");
1429    }
1430    return generateABCForVariant(activeVariant, 1);
1431  }, [exportScope, generateABCForVariant, activeVariant]);
1432
1433  // Helper to generate Vortex Tracker II / ProTracker 3 (PT3) source
1434  const generatePT3 = useCallback(() => {
1435    let pt3 = `; =========================================================\n`;
1436    pt3 += `; ProTracker 3.xx / Vortex Tracker II Module Source\n`;
1437    pt3 += `; Title: Tome of the Dead - ${activeVariant.name}\n`;
1438    pt3 += `; Chip: AY-3-8912 (1.773400 MHz), Stereo ACB / Mono\n`;
1439    pt3 += `; Tempo: ${bpm} BPM (Interrupt: 50 Hz, Speed: 6)\n`;
1440    pt3 += `; Channels: A = Alto, B = Soprano, C = Bass\n`;
1441    pt3 += `; =========================================================\n\n`;
1442    pt3 += `[Module]\nTitle=Tome of the Dead\nAuthor=Producer\nTempo=${bpm}\nSpeed=6\n\n`;
1443    pt3 += `[Patterns]\n`;
1444
1445    const getNoteAtTime = (notes: (Note & { startBeat: number; endBeat: number })[], beat: number) => {
1446      return notes.find((n) => beat >= n.startBeat && beat < n.endBeat) || null;
1447    };
1448
1449    const fmtNote = (n: Note | null) => {
1450      if (!n || n.pitch === "R") return "... ...";
1451      const p = n.pitch.replace("#", "+");
1452      const pad = p.padEnd(3, "-");
1453      const vol = n.staccato ? "v09" : "v14";
1454      return `${pad} ${vol}`;
1455    };
1456
1457    for (let pat = 0; pat < 4; pat++) {
1458      pt3 += `Pattern ${pat}:\n; Row | Chan A (Alto)    | Chan B (Soprano) | Chan C (Bass)     |\n`;
1459      for (let r = 0; r < 32; r++) {
1460        const curBeat = (pat * 32 + r) * 0.5;
1461        const nA = getNoteAtTime(voiceSchedules.A, curBeat);
1462        const nB = getNoteAtTime(voiceSchedules.B, curBeat);
1463        const nC = getNoteAtTime(voiceSchedules.C, curBeat);
1464        pt3 += `${r.toString().padStart(2, "0")}: | ${fmtNote(nA)} | ${fmtNote(nB)} | ${fmtNote(nC)} |\n`;
1465      }
1466      pt3 += `\n`;
1467    }
1468    pt3 += `; End of Module (32 Bars Complete Loop)\n`;
1469    return pt3;
1470  }, [activeVariant, bpm, voiceSchedules]);
1471
1472  // Individual file download helper
1473  const downloadSingleFile = (filename: string, content: string, mimeType = "text/plain") => {
1474    const blob = new Blob([content], { type: mimeType });
1475    const url = URL.createObjectURL(blob);
1476    const a = document.createElement("a");
1477    a.href = url;
1478    a.download = filename;
1479    document.body.appendChild(a);
1480    a.click();
1481    document.body.removeChild(a);
1482    URL.revokeObjectURL(url);
1483  };
1484
1485  // Current exported string content
1486  const exportContent = useMemo(() => {
1487    if (exportFormat === "ABC") return generateABC();
1488    if (exportFormat === "PT3") return generatePT3();
1489    return JSON.stringify(
1490      {
1491        fugue: "Tome of the Dead - 3 Voice Fugue in D minor",
1492        variant: activeVariant.name,
1493        tempo_bpm: bpm,
1494        voices: {
1495          voice_1_alto: activeVariant.v1,
1496          voice_2_soprano: activeVariant.v2,
1497          voice_3_bass: activeVariant.v3,
1498        },
1499      },
1500      null,
1501      2
1502    );
1503  }, [exportFormat, generateABC, generatePT3, activeVariant, bpm]);
1504
1505  const copyToClipboard = () => {
1506    navigator.clipboard.writeText(exportContent);
1507    setCopiedCode(true);
1508    setTimeout(() => setCopiedCode(false), 2000);
1509  };
1510
1511  const handleDownload = () => {
1512    const ext = exportFormat === "ABC" ? "abc" : exportFormat === "PT3" ? "pt3.txt" : "json";
1513    const mime = exportFormat === "ABC" ? "text/vnd.abc" : "text/plain";
1514    const filename = `tome_of_the_dead_${activeVariant.id}.${ext}`;
1515    downloadSingleFile(filename, exportContent, mime);
1516  };
1517
1518  return (
1519    <div
1520      className="min-h-screen w-full flex flex-col items-center justify-center p-3 sm:p-6 transition-colors duration-200 select-none font-mono"
1521      style={{ backgroundColor: SPECTRUM_BORDER_COLORS[borderColorIdx].hex }}
1522    >
1523      {/* ZX Spectrum Screen Box (Main 256x192 styled container) */}
1524      <div className="w-full max-w-4xl bg-black border-4 border-neutral-800 rounded-lg shadow-2xl overflow-hidden flex flex-col text-neutral-100">
1525        
1526        {/* Top Header with Sinclair Colors Rainbow */}
1527        <div className="bg-neutral-900 border-b border-neutral-800 px-4 py-2 flex flex-wrap items-center justify-between gap-2">
1528          <div className="flex items-center gap-3">
1529            {/* Sinclair 4-color diagnostic stripe */}
1530            <div className="flex h-5 w-8 rounded-sm overflow-hidden border border-neutral-700 shadow-inner">
1531              <div className="w-2 bg-[#D70000]"></div>
1532              <div className="w-2 bg-[#D7D700]"></div>
1533              <div className="w-2 bg-[#00D700]"></div>
1534              <div className="w-2 bg-[#00D7D7]"></div>
1535            </div>
1536            <div>
1537              <span className="font-bold text-sm tracking-wider text-cyan-400">Sinclair ZX Spectrum +2 128K</span>
1538              <span className="text-xs text-neutral-400 ml-2 hidden sm:inline">AY-3-8912 SOUND GENERATOR</span>
1539            </div>
1540          </div>
1541          <div className="flex items-center gap-2">
1542            <button
1543              onClick={() => setShowExportModal(!showExportModal)}
1544              className="text-xs px-2.5 py-1 bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-700 rounded transition flex items-center gap-1.5 font-bold shadow-sm"
1545            >
1546              <Download className="w-3.5 h-3.5" />
1547              EXPORT ABC / PT3
1548            </button>
1549            <button
1550              onClick={cycleBorder}
1551              className="text-xs px-2 py-1 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-neutral-700 rounded transition"
1552              title="Change ZX Spectrum Border Color"
1553            >
1554              BORDER {borderColorIdx}
1555            </button>
1556            <span className="text-xs text-emerald-400 bg-neutral-950 px-2 py-1 rounded border border-emerald-900/50">
1557              RAM: 128KB OK
1558            </span>
1559          </div>
1560        </div>
1561
1562        {/* Modal: Export Fugue Score Data (ABC / PT3 / JSON) */}
1563        {showExportModal && (
1564          <div className="p-4 bg-neutral-950 border-b border-neutral-800 relative animate-fadeIn max-h-[85vh] overflow-y-auto">
1565            <div className="flex flex-wrap items-center justify-between gap-2 mb-3 pb-2 border-b border-neutral-800">
1566              <div className="flex items-center gap-2">
1567                <Sparkles className="w-4 h-4 text-amber-400" />
1568                <span className="text-xs font-bold text-cyan-400">
1569                  EXPORT / DOWNLOAD MANAGER:
1570                </span>
1571                <div className="flex gap-1 ml-2">
1572                  <button
1573                    onClick={() => setExportTab("INDIVIDUAL")}
1574                    className={`text-xs px-2.5 py-1 rounded font-bold border transition ${
1575                      exportTab === "INDIVIDUAL"
1576                        ? "bg-cyan-600 text-black border-cyan-400 shadow-sm"
1577                        : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:text-white"
1578                    }`}
1579                  >
1580                    📁 INDIVIDUAL FILE DOWNLOADS
1581                  </button>
1582                  <button
1583                    onClick={() => setExportTab("VIEWER")}
1584                    className={`text-xs px-2.5 py-1 rounded font-bold border transition ${
1585                      exportTab === "VIEWER"
1586                        ? "bg-cyan-600 text-black border-cyan-400 shadow-sm"
1587                        : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:text-white"
1588                    }`}
1589                  >
1590                    📄 CODE VIEWER & BUNDLES
1591                  </button>
1592                </div>
1593              </div>
1594
1595              <button
1596                onClick={() => setShowExportModal(false)}
1597                className="text-xs text-neutral-400 hover:text-white px-2 py-1 bg-neutral-900 border border-neutral-800 rounded"
1598              >
1599                ✕ CLOSE
1600              </button>
1601            </div>
1602
1603            {/* TAB 1: INDIVIDUAL FILE DOWNLOADS (ONE BY ONE) */}
1604            {exportTab === "INDIVIDUAL" && (
1605              <div className="space-y-4">
1606                {/* 6 Short Dungeon Melodies */}
1607                <div>
1608                  <div className="flex items-center justify-between mb-2">
1609                    <span className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
1610                      <Skull className="w-3.5 h-3.5" />
1611                      SHORT F MINOR DUNGEON MELODIES & CUES (DOWNLOAD ONE BY ONE):
1612                    </span>
1613                    <span className="text-[10px] text-neutral-400">All 3 Voices • AY-3-8912 • F minor</span>
1614                  </div>
1615                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
1616                    {GAME_CUES.map((cue) => {
1617                      const cueAbc = `%abc-2.1\nX:1\nT:Tome of the Dead - ${cue.name}\nC:ZX Spectrum 128K AY-3-8912 Chiptune\nM:4/4\nL:1/8\nQ:1/4=${cue.defaultBpm}\nK:Fm\n%%score (V1 V2) V3\nV:V1 clef=treble name="Channel A (Alto)"\n${cue.v1.map((n) => `${n.pitch.replace("Db", "_d").replace("Ab", "_a").replace("Bb", "_b").replace("Eb", "_e").replace("Gb", "_g").replace("E4", "=e").replace("E5", "=e'").replace("F4", "f").replace("C5", "c'").replace("F5", "f'").replace("C4", "c").replace("G4", "g")}${n.duration === 0.5 ? "" : n.duration === 1.0 ? "2" : "4"}`).join(" ")} |]\nV:V2 clef=treble name="Channel B (Soprano)"\n${cue.v2.map((n) => `${n.pitch.replace("Db", "_d").replace("Ab", "_a").replace("Bb", "_b").replace("Eb", "_e").replace("Gb", "_g").replace("E4", "=e").replace("E5", "=e'").replace("F4", "f").replace("C5", "c'").replace("F5", "f'").replace("C4", "c").replace("G4", "g")}${n.duration === 0.5 ? "" : n.duration === 1.0 ? "2" : "4"}`).join(" ")} |]\nV:V3 clef=bass name="Channel C (Basso)"\n${cue.v3.map((n) => `${n.pitch.replace("F2", "F,").replace("C3", "C").replace("Ab2", "_A,").replace("Db3", "_D").replace("Bb2", "_B,").replace("G2", "G,").replace("E2", "=E,").replace("C2", "C,").replace("F3", "F").replace("Db2", "_D,").replace("Bb3", "_B").replace("Ab3", "_A")}${n.duration === 0.5 ? "" : n.duration === 1.0 ? "2" : "4"}`).join(" ")} |]`;
1618
1619                      return (
1620                        <div
1621                          key={cue.id}
1622                          className="p-2.5 bg-neutral-900 border border-neutral-800 rounded flex items-center justify-between gap-2 hover:border-neutral-700 transition"
1623                        >
1624                          <div className="flex items-center gap-2 min-w-0">
1625                            {cue.icon === "crawl" && <Compass className="w-4 h-4 text-cyan-400 shrink-0" />}
1626                            {cue.icon === "danger" && <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />}
1627                            {cue.icon === "swords" && <Swords className="w-4 h-4 text-orange-400 shrink-0" />}
1628                            {cue.icon === "check" && <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />}
1629                            {cue.icon === "trophy" && <Trophy className="w-4 h-4 text-amber-400 shrink-0" />}
1630                            {cue.icon === "skull" && <Skull className="w-4 h-4 text-rose-400 shrink-0" />}
1631                            <div className="min-w-0">
1632                              <div className="text-xs font-bold text-neutral-200 truncate">{cue.name}</div>
1633                              <div className="text-[10px] text-neutral-400 truncate">
1634                                {cue.totalBeats / 4} Bars ({cue.totalBeats}b) • {cue.defaultBpm} BPM
1635                              </div>
1636                            </div>
1637                          </div>
1638
1639                          <div className="flex items-center gap-1.5 shrink-0">
1640                            <button
1641                              onClick={() => {
1642                                navigator.clipboard.writeText(cueAbc);
1643                                setCopiedCode(true);
1644                                setTimeout(() => setCopiedCode(false), 2000);
1645                              }}
1646                              className="px-2 py-1 bg-neutral-800 hover:bg-neutral-700 text-[10px] text-neutral-300 rounded border border-neutral-700"
1647                              title="Copy ABC to Clipboard"
1648                            >
1649                              COPY
1650                            </button>
1651                            <button
1652                              onClick={() => downloadSingleFile(`tome_${cue.id}.abc`, cueAbc, "text/vnd.abc")}
1653                              className="px-2 py-1 bg-cyan-900 hover:bg-cyan-800 text-[10px] font-bold text-cyan-200 rounded border border-cyan-700 flex items-center gap-1"
1654                              title="Download single .abc file"
1655                            >
1656                              <Download className="w-3 h-3" />
1657                              .ABC
1658                            </button>
1659                            <button
1660                              onClick={() => downloadSingleFile(`tome_${cue.id}.pt3.txt`, generateCuePT3(cue), "text/plain")}
1661                              className="px-2 py-1 bg-amber-900 hover:bg-amber-800 text-[10px] font-bold text-amber-200 rounded border border-amber-700 flex items-center gap-1"
1662                              title="Download single .pt3 tracker text file"
1663                            >
1664                              <Download className="w-3 h-3" />
1665                              .PT3
1666                            </button>
1667                          </div>
1668                        </div>
1669                      );
1670                    })}
1671                  </div>
1672                </div>
1673
1674                {/* 7 Background Fugue Variations */}
1675                <div className="pt-2 border-t border-neutral-800">
1676                  <div className="flex items-center justify-between mb-2">
1677                    <span className="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
1678                      <Music className="w-3.5 h-3.5" />
1679                      FULL 32-BAR FUGUE VARIATIONS (DOWNLOAD ONE BY ONE):
1680                    </span>
1681                    <span className="text-[10px] text-neutral-400">Complete 3-Voice Polyphony (128 beats)</span>
1682                  </div>
1683                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
1684                    {THEME_VARIANTS.map((variant, idx) => {
1685                      const variantAbc = generateABCForVariant(variant, idx + 1);
1686                      return (
1687                        <div
1688                          key={variant.id}
1689                          className="p-2.5 bg-neutral-900 border border-neutral-800 rounded flex items-center justify-between gap-2 hover:border-neutral-700 transition"
1690                        >
1691                          <div className="min-w-0">
1692                            <div className="text-xs font-bold text-neutral-200 truncate">{variant.name}</div>
1693                            <div className="text-[10px] text-neutral-400 truncate">
1694                              Key: {variant.keyName} • 32 Measures (4/4) • 74 BPM
1695                            </div>
1696                          </div>
1697
1698                          <div className="flex items-center gap-1.5 shrink-0">
1699                            <button
1700                              onClick={() => {
1701                                navigator.clipboard.writeText(variantAbc);
1702                                setCopiedCode(true);
1703                                setTimeout(() => setCopiedCode(false), 2000);
1704                              }}
1705                              className="px-2 py-1 bg-neutral-800 hover:bg-neutral-700 text-[10px] text-neutral-300 rounded border border-neutral-700"
1706                              title="Copy ABC to Clipboard"
1707                            >
1708                              COPY
1709                            </button>
1710                            <button
1711                              onClick={() => downloadSingleFile(`tome_fugue_${variant.id}.abc`, variantAbc, "text/vnd.abc")}
1712                              className="px-2 py-1 bg-emerald-900 hover:bg-emerald-800 text-[10px] font-bold text-emerald-200 rounded border border-emerald-700 flex items-center gap-1"
1713                              title="Download single .abc file"
1714                            >
1715                              <Download className="w-3 h-3" />
1716                              .ABC
1717                            </button>
1718                            <button
1719                              onClick={() => downloadSingleFile(`tome_fugue_${variant.id}.pt3.txt`, generateVariantPT3(variant), "text/plain")}
1720                              className="px-2 py-1 bg-amber-900 hover:bg-amber-800 text-[10px] font-bold text-amber-200 rounded border border-amber-700 flex items-center gap-1"
1721                              title="Download single .pt3 tracker text file"
1722                            >
1723                              <Download className="w-3 h-3" />
1724                              .PT3
1725                            </button>
1726                          </div>
1727                        </div>
1728                      );
1729                    })}
1730                  </div>
1731                </div>
1732              </div>
1733            )}
1734
1735            {/* TAB 2: CODE VIEWER & BUNDLES */}
1736            {exportTab === "VIEWER" && (
1737              <div>
1738                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
1739                  <div className="flex flex-wrap items-center gap-2">
1740                    <span className="text-xs font-bold text-neutral-400">FORMAT:</span>
1741                    <div className="flex gap-1">
1742                      {(["ABC", "PT3", "JSON"] as const).map((fmt) => (
1743                        <button
1744                          key={fmt}
1745                          onClick={() => setExportFormat(fmt)}
1746                          className={`text-xs px-2 py-0.5 rounded font-bold border transition ${
1747                            exportFormat === fmt
1748                              ? "bg-cyan-600 text-black border-cyan-400 shadow-sm"
1749                              : "bg-neutral-900 text-neutral-400 border-neutral-700 hover:text-white"
1750                          }`}
1751                        >
1752                          {fmt === "ABC" ? "ABC NOTATION" : fmt === "PT3" ? "PT3 TRACKER" : "RAW JSON"}
1753                        </button>
1754                      ))}
1755                    </div>
1756
1757                    {exportFormat === "ABC" && (
1758                      <div className="flex gap-1 ml-2 pl-2 border-l border-neutral-700">
1759                        <button
1760                          onClick={() => setExportScope("CURRENT")}
1761                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold border transition ${
1762                            exportScope === "CURRENT"
1763                              ? "bg-amber-500 text-black border-amber-400"
1764                              : "bg-neutral-900 text-neutral-400 border-neutral-800 hover:text-white"
1765                          }`}
1766                        >
1767                          CURRENT KEY [{activeVariant.key}]
1768                        </button>
1769                        <button
1770                          onClick={() => setExportScope("ALL")}
1771                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold border transition ${
1772                            exportScope === "ALL"
1773                              ? "bg-amber-500 text-black border-amber-400"
1774                              : "bg-neutral-900 text-neutral-400 border-neutral-800 hover:text-white"
1775                          }`}
1776                        >
1777                          ALL VARIATIONS (SONGBOOK)
1778                        </button>
1779                      </div>
1780                    )}
1781                  </div>
1782
1783                  <div className="flex items-center gap-2">
1784                    <button
1785                      onClick={copyToClipboard}
1786                      className="px-2.5 py-1 bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-200 border border-neutral-700 rounded flex items-center gap-1 transition"
1787                    >
1788                      {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
1789                      {copiedCode ? "COPIED!" : "COPY"}
1790                    </button>
1791                    <button
1792                      onClick={handleDownload}
1793                      className="px-2.5 py-1 bg-emerald-800 hover:bg-emerald-700 text-xs text-white border border-emerald-600 rounded flex items-center gap-1 transition font-bold"
1794                    >
1795                      <Download className="w-3.5 h-3.5" />
1796                      DOWNLOAD .{exportFormat === "ABC" ? "ABC" : exportFormat === "PT3" ? "PT3" : "JSON"}
1797                    </button>
1798                  </div>
1799                </div>
1800
1801                <pre className="text-[10px] bg-neutral-900 border border-neutral-800 p-3 rounded max-h-56 overflow-y-auto text-emerald-400 font-mono">
1802                  {exportContent}
1803                </pre>
1804              </div>
1805            )}
1806          </div>
1807        )}
1808
1809        {/* Title & Game Header */}
1810        <div className="p-4 sm:p-5 border-b border-neutral-800 bg-gradient-to-b from-neutral-950 to-neutral-900">
1811          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
1812            <div>
1813              <div className="flex items-center gap-2">
1814                <Skull className="w-5 h-5 text-rose-500 animate-pulse" />
1815                <h1 className="text-xl sm:text-2xl font-black tracking-widest text-neutral-100 uppercase">
1816                  TOME OF THE DEAD
1817                </h1>
1818                <span className="text-xs bg-rose-950 text-rose-300 border border-rose-800 px-1.5 py-0.5 rounded">
1819                  DUNGEON CRAWLER OST
1820                </span>
1821              </div>
1822              <p className="text-xs text-neutral-400 mt-1 flex items-center gap-1.5">
1823                <BookOpen className="w-3.5 h-3.5 text-neutral-500" />
1824                {activeVariant.subtitle}
1825              </p>
1826            </div>
1827
1828            {/* Current Section & Harmonic Concordance Banner */}
1829            <div className="bg-neutral-900 border border-neutral-700 rounded p-2.5 text-right flex flex-col items-end gap-1">
1830              <div className="flex items-center gap-2">
1831                <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider">
1832                  BAR {currentBar} / 32 • BEAT {Math.floor(currentBeat) + 1}
1833                </span>
1834                <span className="text-[9px] px-1.5 py-0.2 bg-cyan-950 text-cyan-300 border border-cyan-800 rounded font-bold">
1835                  {selectedVariantId === "f_minor_staccato_theme" ? "STACCATO THEME / LEGATO ACCOMP" : "PURE LEGATO"}
1836                </span>
1837                <span className="text-[9px] px-1.5 py-0.2 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded font-bold">
1838                  CONSONANT
1839                </span>
1840              </div>
1841              <div className="text-xs font-semibold text-amber-300 truncate max-w-[320px]">
1842                {currentSection.name}
1843              </div>
1844              <div className="flex items-center gap-1.5 mt-0.5">
1845                <span className="text-[10px] text-neutral-400">KEY: {activeVariant.keyName} |</span>
1846                <span
1847                  className={`text-[11px] font-bold px-2 py-0.5 rounded border ${
1848                    currentChord.isSept
1849                      ? "bg-amber-950 text-amber-300 border-amber-600 animate-pulse"
1850                      : currentChord.isDominant
1851                      ? "bg-emerald-950 text-emerald-300 border-emerald-700"
1852                      : "bg-neutral-950 text-cyan-300 border-neutral-800"
1853                  }`}
1854                >
1855                  {currentChord.chord}
1856                </span>
1857              </div>
1858            </div>
1859          </div>
1860
1861          {/* Theme Variant Selector Sub-Bar */}
1862          <div className="mt-3 pt-3 border-t border-neutral-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
1863            <span className="text-xs text-neutral-400 font-bold flex items-center gap-1">
1864              <Layers className="w-3.5 h-3.5 text-cyan-400" />
1865              BACKGROUND FUGUE VARIANT:
1866            </span>
1867            <div className="flex flex-wrap gap-1">
1868              {THEME_VARIANTS.map((v) => (
1869                <button
1870                  key={v.id}
1871                  onClick={() => {
1872                    setSelectedVariantId(v.id);
1873                    setPlaybackMode("FUGUE");
1874                    setCurrentBeat(0);
1875                    currentBeatRef.current = 0;
1876                  }}
1877                  className={`text-[11px] px-2 py-0.5 rounded font-bold border transition ${
1878                    playbackMode === "FUGUE" && selectedVariantId === v.id
1879                      ? "bg-cyan-600 text-black border-cyan-400 shadow-sm"
1880                      : "bg-neutral-800 text-neutral-300 border-neutral-700 hover:bg-neutral-700"
1881                  }`}
1882                >
1883                  {v.name.split(". ")[1] || v.name}
1884                </button>
1885              ))}
1886            </div>
1887          </div>
1888
1889          {/* Interactive F Minor Short Game Cues / Stingers Panel */}
1890          <div className="mt-3 pt-3 border-t border-neutral-800 flex flex-col gap-2">
1891            <div className="flex flex-wrap items-center justify-between gap-2">
1892              <span className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
1893                <Skull className="w-3.5 h-3.5" />
1894                F MINOR MODULAR GAME CUES & JINGLES (AY-3-8912):
1895              </span>
1896              <div className="flex items-center gap-1.5">
1897                {/* Loop Mode / Chain Story Mode Toggle */}
1898                {playbackMode === "CUE" && (
1899                  <div className="flex items-center bg-neutral-900 border border-neutral-800 rounded p-0.5 text-[10px]">
1900                    <button
1901                      onClick={() => setCuePlayMode("LOOP_SINGLE")}
1902                      className={`px-2 py-0.5 rounded font-bold transition ${
1903                        cuePlayMode === "LOOP_SINGLE"
1904                          ? "bg-rose-950 text-rose-300 border border-rose-700"
1905                          : "text-neutral-400 hover:text-white"
1906                      }`}
1907                      title="Loop active cue continuously"
1908                    >
1909                      🔁 LOOP ACTIVE
1910                    </button>
1911                    <button
1912                      onClick={() => setCuePlayMode("CHAIN_STORY")}
1913                      className={`px-2 py-0.5 rounded font-bold transition ${
1914                        cuePlayMode === "CHAIN_STORY"
1915                          ? "bg-amber-950 text-amber-300 border border-amber-700"
1916                          : "text-neutral-400 hover:text-white"
1917                      }`}
1918                      title="Seamlessly auto-chain cues like a dungeon story"
1919                    >
1920                      🔀 AUTO-CHAIN STORY
1921                    </button>
1922                  </div>
1923                )}
1924
1925                {playbackMode === "CUE" && (
1926                  <button
1927                    onClick={returnToFugue}
1928                    className="text-xs px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 text-cyan-300 border border-neutral-600 rounded flex items-center gap-1 font-bold"
1929                  >
1930                    <ArrowLeft className="w-3 h-3" />
1931                    MAIN FUGUE
1932                  </button>
1933                )}
1934              </div>
1935            </div>
1936
1937            {/* Seamless Transition Banner */}
1938            {nextQueuedCueId && (
1939              <div className="text-[10px] bg-amber-950/60 border border-amber-800/80 px-2.5 py-1 rounded text-amber-300 flex items-center justify-between">
1940                <span>
1941                  QUANTIZED TRANSITION: Will transition seamlessly to <strong className="uppercase">{nextQueuedCueId.replace("_", " ")}</strong> at next phrase boundary!
1942                </span>
1943                <button
1944                  onClick={() => playCue(nextQueuedCueId, true)}
1945                  className="underline hover:text-white font-bold ml-2"
1946                >
1947                  Switch Now
1948                </button>
1949              </div>
1950            )}
1951
1952            <div className="grid grid-cols-2 sm:grid-cols-6 gap-1.5">
1953              {GAME_CUES.map((cue) => {
1954                const isSelected = playbackMode === "CUE" && selectedCueId === cue.id;
1955                const isQueued = nextQueuedCueId === cue.id;
1956                return (
1957                  <button
1958                    key={cue.id}
1959                    onClick={() => playCue(cue.id)}
1960                    className={`p-2 rounded border text-left transition flex flex-col gap-1 relative overflow-hidden ${
1961                      isSelected
1962                        ? "bg-rose-950 border-rose-500 shadow-md shadow-rose-950/40 text-rose-100"
1963                        : isQueued
1964                        ? "bg-amber-950 border-amber-500 text-amber-200 animate-pulse"
1965                        : "bg-neutral-900 border-neutral-800 hover:bg-neutral-850 hover:border-neutral-700 text-neutral-300"
1966                    }`}
1967                  >
1968                    <div className="flex items-center justify-between">
1969                      <div className="flex items-center gap-1.5">
1970                        {cue.icon === "crawl" && <Compass className="w-3.5 h-3.5 text-cyan-400" />}
1971                        {cue.icon === "danger" && <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />}
1972                        {cue.icon === "swords" && <Swords className="w-3.5 h-3.5 text-orange-400" />}
1973                        {cue.icon === "check" && <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />}
1974                        {cue.icon === "trophy" && <Trophy className="w-3.5 h-3.5 text-amber-400" />}
1975                        {cue.icon === "skull" && <Skull className="w-3.5 h-3.5 text-rose-400" />}
1976                        <span className="text-xs font-bold truncate">{cue.name}</span>
1977                      </div>
1978                      {isSelected && isPlaying && (
1979                        <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping"></span>
1980                      )}
1981                      {isQueued && (
1982                        <span className="text-[8px] bg-amber-400 text-black px-1 rounded font-bold">NEXT</span>
1983                      )}
1984                    </div>
1985                    <span className="text-[9px] text-neutral-400 line-clamp-1">{cue.subtitle.split("•")[1] || cue.subtitle}</span>
1986                    <div className="flex items-center justify-between text-[9px] text-neutral-500 mt-0.5">
1987                      <span>{cue.totalBeats / 4} Bars ({(cue.totalBeats)}b)</span>
1988                      <span>{cue.defaultBpm} BPM</span>
1989                    </div>
1990                  </button>
1991                );
1992              })}
1993            </div>
1994          </div>
1995        </div>
1996
1997        {/* Realtime 3-Channel AY-3-8912 Dashboard */}
1998        <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-3 bg-neutral-950 border-b border-neutral-800">
1999          
2000          {/* Channel A: Alto / Voice 1 */}
2001          <div className={`p-3 rounded border transition-all ${
2002            channelMutes.A ? "bg-neutral-900/40 border-neutral-800 opacity-60" : "bg-neutral-900 border-cyan-800/80 shadow-cyan-950/20 shadow-md"
2003          }`}>
2004            <div className="flex items-center justify-between mb-2">
2005              <span className="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
2006                <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></div>
2007                CHANNEL A: ALTO
2008              </span>
2009              <div className="flex items-center gap-1 text-[10px]">
2010                <button
2011                  onClick={() => toggleMute("A")}
2012                  className={`px-1.5 py-0.5 rounded border ${channelMutes.A ? "bg-rose-950 text-rose-300 border-rose-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2013                >
2014                  MUTE
2015                </button>
2016                <button
2017                  onClick={() => toggleSolo("A")}
2018                  className={`px-1.5 py-0.5 rounded border ${channelSolos.A ? "bg-amber-950 text-amber-300 border-amber-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2019                >
2020                  SOLO
2021                </button>
2022              </div>
2023            </div>
2024            <div className="flex items-baseline justify-between mb-2">
2025              <span className="text-2xl font-black text-cyan-300 font-mono tracking-wider">
2026                {activeNotes.A !== "-" ? activeNotes.A : "REST"}
2027              </span>
2028              <span className="text-xs text-neutral-400">
2029                {activeNotes.A !== "-" ? `${Math.round(getFreq(activeNotes.A))} Hz` : "0 Hz"}
2030              </span>
2031            </div>
2032            {/* AY-3-8912 16-step Volume DAC display */}
2033            <div className="space-y-1">
2034              <div className="flex justify-between text-[10px] text-neutral-500">
2035                <span>AY VOL LEVEL</span>
2036                <span className="text-cyan-400 font-bold">{activeLevels.A} / 15</span>
2037              </div>
2038              <div className="flex gap-0.5 h-3 bg-neutral-950 p-0.5 rounded border border-neutral-800">
2039                {Array.from({ length: 16 }).map((_, i) => (
2040                  <div
2041                    key={i}
2042                    className={`flex-1 rounded-xs transition-colors duration-75 ${
2043                      i <= activeLevels.A ? "bg-cyan-400 shadow-sm shadow-cyan-400/50" : "bg-neutral-800/40"
2044                    }`}
2045                  />
2046                ))}
2047              </div>
2048            </div>
2049            <div className="mt-2 text-[10px] text-neutral-400 truncate">
2050              {currentBar <= 4 ? "Fugue Subject (Exposition)" : currentBar >= 25 && currentBar <= 28 ? "Stretto Subject" : "Counterpoint & Suspensions"}
2051            </div>
2052          </div>
2053
2054          {/* Channel B: Soprano / Voice 2 */}
2055          <div className={`p-3 rounded border transition-all ${
2056            channelMutes.B ? "bg-neutral-900/40 border-neutral-800 opacity-60" : "bg-neutral-900 border-yellow-800/80 shadow-yellow-950/20 shadow-md"
2057          }`}>
2058            <div className="flex items-center justify-between mb-2">
2059              <span className="text-xs font-bold text-yellow-400 flex items-center gap-1.5">
2060                <div className="w-2.5 h-2.5 rounded-full bg-yellow-400 animate-pulse"></div>
2061                CHANNEL B: SOPRANO
2062              </span>
2063              <div className="flex items-center gap-1 text-[10px]">
2064                <button
2065                  onClick={() => toggleMute("B")}
2066                  className={`px-1.5 py-0.5 rounded border ${channelMutes.B ? "bg-rose-950 text-rose-300 border-rose-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2067                >
2068                  MUTE
2069                </button>
2070                <button
2071                  onClick={() => toggleSolo("B")}
2072                  className={`px-1.5 py-0.5 rounded border ${channelSolos.B ? "bg-amber-950 text-amber-300 border-amber-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2073                >
2074                  SOLO
2075                </button>
2076              </div>
2077            </div>
2078            <div className="flex items-baseline justify-between mb-2">
2079              <span className="text-2xl font-black text-yellow-300 font-mono tracking-wider">
2080                {activeNotes.B !== "-" ? activeNotes.B : "REST"}
2081              </span>
2082              <span className="text-xs text-neutral-400">
2083                {activeNotes.B !== "-" ? `${Math.round(getFreq(activeNotes.B))} Hz` : "0 Hz"}
2084              </span>
2085            </div>
2086            {/* AY-3-8912 16-step Volume DAC display */}
2087            <div className="space-y-1">
2088              <div className="flex justify-between text-[10px] text-neutral-500">
2089                <span>AY VOL LEVEL</span>
2090                <span className="text-yellow-400 font-bold">{activeLevels.B} / 15</span>
2091              </div>
2092              <div className="flex gap-0.5 h-3 bg-neutral-950 p-0.5 rounded border border-neutral-800">
2093                {Array.from({ length: 16 }).map((_, i) => (
2094                  <div
2095                    key={i}
2096                    className={`flex-1 rounded-xs transition-colors duration-75 ${
2097                      i <= activeLevels.B ? "bg-yellow-400 shadow-sm shadow-yellow-400/50" : "bg-neutral-800/40"
2098                    }`}
2099                  />
2100                ))}
2101              </div>
2102            </div>
2103            <div className="mt-2 text-[10px] text-neutral-400 truncate">
2104              {currentBar <= 4 ? "Active Counterpoint" : currentBar <= 8 ? "Fugue Answer in A minor" : currentBar >= 26 ? "Stretto Climax Entry" : "Legato High Voice"}
2105            </div>
2106          </div>
2107
2108          {/* Channel C: Bass / Voice 3 */}
2109          <div className={`p-3 rounded border transition-all ${
2110            channelMutes.C ? "bg-neutral-900/40 border-neutral-800 opacity-60" : "bg-neutral-900 border-emerald-800/80 shadow-emerald-950/20 shadow-md"
2111          }`}>
2112            <div className="flex items-center justify-between mb-2">
2113              <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
2114                <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></div>
2115                CHANNEL C: BASSO
2116              </span>
2117              <div className="flex items-center gap-1 text-[10px]">
2118                <button
2119                  onClick={() => toggleMute("C")}
2120                  className={`px-1.5 py-0.5 rounded border ${channelMutes.C ? "bg-rose-950 text-rose-300 border-rose-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2121                >
2122                  MUTE
2123                </button>
2124                <button
2125                  onClick={() => toggleSolo("C")}
2126                  className={`px-1.5 py-0.5 rounded border ${channelSolos.C ? "bg-amber-950 text-amber-300 border-amber-700" : "bg-neutral-800 text-neutral-400 border-neutral-700"}`}
2127                >
2128                  SOLO
2129                </button>
2130              </div>
2131            </div>
2132            <div className="flex items-baseline justify-between mb-2">
2133              <span className="text-2xl font-black text-emerald-300 font-mono tracking-wider">
2134                {activeNotes.C !== "-" ? activeNotes.C : "REST"}
2135              </span>
2136              <span className="text-xs text-neutral-400">
2137                {activeNotes.C !== "-" ? `${Math.round(getFreq(activeNotes.C))} Hz` : "0 Hz"}
2138              </span>
2139            </div>
2140            {/* AY-3-8912 16-step Volume DAC display */}
2141            <div className="space-y-1">
2142              <div className="flex justify-between text-[10px] text-neutral-500">
2143                <span>AY VOL LEVEL</span>
2144                <span className="text-emerald-400 font-bold">{activeLevels.C} / 15</span>
2145              </div>
2146              <div className="flex gap-0.5 h-3 bg-neutral-950 p-0.5 rounded border border-neutral-800">
2147                {Array.from({ length: 16 }).map((_, i) => (
2148                  <div
2149                    key={i}
2150                    className={`flex-1 rounded-xs transition-colors duration-75 ${
2151                      i <= activeLevels.C ? "bg-emerald-400 shadow-sm shadow-emerald-400/50" : "bg-neutral-800/40"
2152                    }`}
2153                  />
2154                ))}
2155              </div>
2156            </div>
2157            <div className="mt-2 text-[10px] text-neutral-400 truncate">
2158              {currentBar <= 8 ? "Active Ground Bass" : currentBar >= 13 && currentBar <= 16 ? "Staccato Walking Bass" : currentBar >= 25 ? "Organ Pedal Point" : "Bass Subject Counterpoint"}
2159            </div>
2160          </div>
2161        </div>
2162
2163        {/* Real-time Visual Counterpoint Tracker / Piano Roll */}
2164        <div className="p-4 bg-neutral-950 border-b border-neutral-800">
2165          <div className="flex items-center justify-between mb-2 text-xs text-neutral-400">
2166            <span className="flex items-center gap-1.5 font-bold text-neutral-300">
2167              <Music className="w-3.5 h-3.5 text-cyan-400" />
2168              POLYPHONIC COUNTERPOINT TRACKER
2169            </span>
2170            <div className="flex items-center gap-3 text-[11px]">
2171              <span className="flex items-center gap-1">
2172                <span className="w-2 h-2 rounded-xs bg-cyan-400 inline-block"></span> V1 (Alto)
2173              </span>
2174              <span className="flex items-center gap-1">
2175                <span className="w-2 h-2 rounded-xs bg-yellow-400 inline-block"></span> V2 (Soprano)
2176              </span>
2177              <span className="flex items-center gap-1">
2178                <span className="w-2 h-2 rounded-xs bg-emerald-400 inline-block"></span> V3 (Bass)
2179              </span>
2180            </div>
2181          </div>
2182
2183          {/* 32-Bar Measure Progress Bar */}
2184          <div className="relative w-full h-8 bg-neutral-900 border border-neutral-800 rounded overflow-hidden mb-3">
2185            {/* Section blocks */}
2186            <div className="absolute inset-0 flex text-[9px] text-neutral-500 divide-x divide-neutral-800">
2187              {FUGUE_SECTIONS.map((sec, idx) => (
2188                <div
2189                  key={idx}
2190                  className={`flex-1 flex items-center justify-center truncate px-1 transition-colors ${
2191                    currentBar >= sec.startBar && currentBar <= sec.endBar ? "bg-cyan-950/40 text-cyan-300 font-bold" : ""
2192                  }`}
2193                  title={`${sec.name}: Bars ${sec.startBar}-${sec.endBar}`}
2194                >
2195                  B{sec.startBar}-{sec.endBar}
2196                </div>
2197              ))}
2198            </div>
2199
2200            {/* Playhead Indicator */}
2201            <div
2202              className="absolute top-0 bottom-0 w-1 bg-rose-500 shadow-md shadow-rose-500/80 transition-all z-10"
2203              style={{ left: `${(currentBeat / 128) * 100}%` }}
2204            />
2205          </div>
2206
2207          {/* Active 3-Voice Pitch Range Visualizer */}
2208          <div className="bg-neutral-900 border border-neutral-800 rounded p-2.5 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
2209            <div className="flex items-center justify-between bg-neutral-950 px-2.5 py-1.5 rounded border border-neutral-800">
2210              <span className="text-cyan-400 font-bold">V1 Legato Lead:</span>
2211              <span className="font-mono text-neutral-200">
2212                {activeNotes.A !== "-" ? `♪ ${activeNotes.A} (Key: Dm)` : "—"}
2213              </span>
2214            </div>
2215            <div className="flex items-center justify-between bg-neutral-950 px-2.5 py-1.5 rounded border border-neutral-800">
2216              <span className="text-yellow-400 font-bold">V2 Answer/Suspension:</span>
2217              <span className="font-mono text-neutral-200">
2218                {activeNotes.B !== "-" ? `♪ ${activeNotes.B} (Key: Am)` : "—"}
2219              </span>
2220            </div>
2221            <div className="flex items-center justify-between bg-neutral-950 px-2.5 py-1.5 rounded border border-neutral-800">
2222              <span className="text-emerald-400 font-bold">V3 Bass / Pedal:</span>
2223              <span className="font-mono text-neutral-200">
2224                {activeNotes.C !== "-" ? `♪ ${activeNotes.C} (Low Bass)` : "—"}
2225              </span>
2226            </div>
2227          </div>
2228        </div>
2229
2230        {/* Master Control Panel */}
2231        <div className="p-4 sm:p-5 bg-neutral-900 flex flex-col gap-4">
2232          <div className="flex flex-wrap items-center justify-between gap-4">
2233            
2234            {/* Primary Transport Controls */}
2235            <div className="flex items-center gap-2">
2236              <button
2237                onClick={togglePlay}
2238                className={`flex items-center gap-2 px-5 py-2.5 rounded font-bold text-sm tracking-wide transition shadow-lg ${
2239                  isPlaying
2240                    ? "bg-amber-600 hover:bg-amber-500 text-white shadow-amber-900/30"
2241                    : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/30"
2242                }`}
2243              >
2244                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
2245                {isPlaying ? "PAUSE" : "PLAY FUGUE"}
2246              </button>
2247
2248              <button
2249                onClick={handleRewind}
2250                className="p-2.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border border-neutral-700 rounded transition"
2251                title="Restart Fugue from Bar 1"
2252              >
2253                <RotateCcw className="w-4 h-4" />
2254              </button>
2255            </div>
2256
2257            {/* Tempo / Adagio Slider (Default 74 BPM) */}
2258            <div className="flex items-center gap-3 bg-neutral-950 border border-neutral-800 px-3 py-1.5 rounded">
2259              <Sliders className="w-4 h-4 text-cyan-400" />
2260              <div className="flex flex-col">
2261                <span className="text-[10px] text-neutral-400">TEMPO</span>
2262                <span className="text-xs font-bold text-neutral-100">{bpm} BPM</span>
2263              </div>
2264              <input
2265                type="range"
2266                min={54}
2267                max={96}
2268                value={bpm}
2269                onChange={(e) => setBpm(Number(e.target.value))}
2270                className="w-24 sm:w-28 accent-cyan-400 cursor-pointer"
2271              />
2272            </div>
2273
2274            {/* Master Volume */}
2275            <div className="flex items-center gap-3 bg-neutral-950 border border-neutral-800 px-3 py-1.5 rounded">
2276              {masterVolume === 0 ? (
2277                <VolumeX className="w-4 h-4 text-rose-400" />
2278              ) : (
2279                <Volume2 className="w-4 h-4 text-emerald-400" />
2280              )}
2281              <div className="flex flex-col">
2282                <span className="text-[10px] text-neutral-400">VOLUME</span>
2283                <span className="text-xs font-bold text-neutral-100">{Math.round(masterVolume * 100)}%</span>
2284              </div>
2285              <input
2286                type="range"
2287                min={0}
2288                max={1}
2289                step={0.05}
2290                value={masterVolume}
2291                onChange={(e) => setMasterVolume(Number(e.target.value))}
2292                className="w-20 sm:w-24 accent-emerald-400 cursor-pointer"
2293              />
2294            </div>
2295          </div>
2296
2297          {/* Sound Timbre & Stereo Mode Selectors */}
2298          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-neutral-800 text-xs">
2299            {/* AY Panning Mode Selector */}
2300            <div className="flex items-center justify-between bg-neutral-950 p-2.5 rounded border border-neutral-800">
2301              <span className="text-neutral-400 flex items-center gap-1.5">
2302                <Radio className="w-3.5 h-3.5 text-neutral-500" />
2303                AY STEREO ROUTING:
2304              </span>
2305              <div className="flex gap-1">
2306                {(["ACB", "ABC", "MONO"] as const).map((mode) => (
2307                  <button
2308                    key={mode}
2309                    onClick={() => setPanningMode(mode)}
2310                    className={`px-2 py-1 rounded text-[11px] font-bold border transition ${
2311                      panningMode === mode
2312                        ? "bg-cyan-950 text-cyan-300 border-cyan-700"
2313                        : "bg-neutral-800 text-neutral-400 border-neutral-700 hover:text-neutral-200"
2314                    }`}
2315                  >
2316                    {mode === "ACB" ? "ACB (128K)" : mode === "ABC" ? "ABC (DEMO)" : "MONO (48K)"}
2317                  </button>
2318                ))}
2319              </div>
2320            </div>
2321
2322            {/* Timbre Engine & Gothic Organ Reverb */}
2323            <div className="flex flex-col gap-2 bg-neutral-950 p-2.5 rounded border border-neutral-800">
2324              <div className="flex items-center justify-between">
2325                <span className="text-neutral-400 flex items-center gap-1.5">
2326                  <Waves className="w-3.5 h-3.5 text-neutral-500" />
2327                  TIMBRE:
2328                </span>
2329                <div className="flex gap-1">
2330                  {(
2331                    [
2332                      { id: "AY_PURE", label: "PURE AY-3" },
2333                      { id: "CRYPT_ORGAN", label: "GOTHIC ORGAN" },
2334                      { id: "HARPSICHORD", label: "HARPSICHORD" },
2335                    ] as const
2336                  ).map((mode) => (
2337                    <button
2338                      key={mode.id}
2339                      onClick={() => setSoundMode(mode.id)}
2340                      className={`px-2 py-1 rounded text-[11px] font-bold border transition ${
2341                        soundMode === mode.id
2342                          ? "bg-amber-950 text-amber-300 border-amber-700"
2343                          : "bg-neutral-800 text-neutral-400 border-neutral-700 hover:text-neutral-200"
2344                      }`}
2345                    >
2346                      {mode.label}
2347                    </button>
2348                  ))}
2349                </div>
2350              </div>
2351
2352              {/* Gothic Organ Reverb Tail Slider */}
2353              {soundMode !== "AY_PURE" && (
2354                <div className="flex items-center justify-between pt-1 border-t border-neutral-800/60">
2355                  <span className="text-[10px] text-amber-400 font-bold">
2356                    CATHEDRAL CRYPT REVERB:
2357                  </span>
2358                  <div className="flex items-center gap-2">
2359                    <input
2360                      type="range"
2361                      min={0}
2362                      max={1}
2363                      step={0.05}
2364                      value={reverbMix}
2365                      onChange={(e) => setReverbMix(Number(e.target.value))}
2366                      className="w-24 accent-amber-400 cursor-pointer"
2367                    />
2368                    <span className="text-[10px] font-mono text-neutral-300 w-8 text-right">
2369                      {Math.round(reverbMix * 100)}%
2370                    </span>
2371                  </div>
2372                </div>
2373              )}
2374            </div>
2375          </div>
2376        </div>
2377
2378        {/* Footer Notes & Dungeon Crawler Lore */}
2379        <div className="px-4 py-2.5 bg-neutral-950 border-t border-neutral-800 text-[11px] text-neutral-500 flex flex-wrap items-center justify-between gap-2">
2380          <div className="flex items-center gap-2">
2381            <Shield className="w-3.5 h-3.5 text-neutral-600" />
2382            <span>TOME OF THE DEAD • AY-3-8912 Chiptune Soundtrack (1.7734 MHz Clock)</span>
2383          </div>
2384          <div>
2385            <span>Key: D minor (Adagio 4/4) • Pure Minor Tonic Cadence on Bar 32</span>
2386          </div>
2387        </div>
2388
2389      </div>
2390    </div>
2391  );
2392}
2393
