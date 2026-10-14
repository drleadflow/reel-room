# Motion v2: the motion system every style shares

Code: `engine/motion/` (`motion.js` runtime, `motion.py` planner, `sfxkit.py` sounds, `mixer.py`), `engine/hdr.py`,
`engine/qa_motion.py`. Wired into the split engine (`templates/split/motionlayer.py`: split-deck, list-stack,
motion-editorial, clean-talk) and the stylekit page (`templates/stylekit/kit.py`: floating-cards, carousel-slideup,
desk-demo, editorial-ui). Nothing to call by hand: compose plans it, render mixes it, QA gates it.

The goal is pro motion that lands on words and carries meaning. Premium, never busy: one hero per beat, motion that
says something, sound that sits under the voice.

## 1. The dial: project.json "motion"

```json
"motion": {"level": "polished", "sfx": "light", "grain": false, "transitions": "auto"}
```

| key | values | default |
|---|---|---|
| `level` | `simple`, `polished`, `showreel` | `polished` |
| `sfx` | `off`, `light`, `full` | `light` |
| `grain` | `true` / `false` (film grain, opt-in polish) | `false` |
| `vignette` | 0 to 0.3 (edge darkening on the speaker) | level default |
| `handheld` | `true` / `false` (subtle handheld drift) | level default |
| `transitions` | `"auto"`, `"off"`, `"every-cut"`, a number (max per 10 s), or `{"per10s": 3, "moves": ["whip", "push"]}` | `"auto"` |
| `captions` | `"auto"`, `"plain"`, `"kinetic"` | level default |
| `still_max` | seconds, overrides the dead-frame limit | level default |
| `behind` | behind-head words (split engine, section 5) | none |
| `parallax` | `[{"sel": "#panel", "k": 0.3}]`: a layer follows the camera at a fraction of its move (depth) | none |

`"motion": false` switches the whole layer off (legacy render, exactly as before Motion v2).

### What each level turns on

| | simple | polished (default) | showreel |
|---|---|---|---|
| idea | cuts + captions + settle | the full system, teaching pace | "show off": a distinct move on every cut |
| settle on every visible cut | 1.03 -> 1 | 1.045 -> 1 | 1.06 -> 1 |
| slow push through each shot | off | +2.5 % (capped by shot length) | +4 % |
| punch on emphasis words | off | 1.06, at least 2.4 s apart | 1.1, at least 1.3 s apart |
| WIDE/CLOSE reframes + punches where the picture would sit still | off | fills stills over 1.05 s, fillers at least 1.2 s apart | fills stills over 0.7 s |
| handheld drift | off | off | on |
| transitions | none | on section cuts (layout or new insert), at most 3.4 per 10 s, cycling whip, zoom, push, iris | every cut, cycling whip, zoom, iris, drop, smash, push, flash, rack |
| captions | plain (as before) | kinetic: words rise in, payoff words stamp | kinetic + giant growth on single payoff words |
| entrance eases | as written | swapped to the snap (expo.out); crawl-in curves fixed | same |
| vignette | 0 | 0.16 | 0.2 |
| graphics per idea | at most 1 (planner rule) | one hero per beat, density targets below | max density, still on brand and inside the safe zone |
| QA targets | dead-frame and density gates exempt | still <= 1.2 s, >= 55 % moving, mean motion >= 4.5, >= 1.2 events/s, hero >= 60 % width | still <= 0.8 s, >= 70 %, >= 6, >= 2 events/s |

### Per-beat override (on the edl.json segment the storyboard beat maps to)

```json
{"id": "f1c", "motion": {"transition": "whip", "camera": "close", "punch": "@fortitude"}}
```

- `level`: `simple`, `polished` or `showreel` for this beat only (written by `engine/rounds.py`). It overrides the reel
  level for the beat's span: settle, push, punch size and spacing, fillers, handheld, caption entrances, the
  transition on the cut INTO the beat, and the density targets the `motion_density`, `dead_frames` and
  `event_density` gates use for that span (`plan.levels`, `qa/motion.json` `levels`). Explicit keys win over the
  level; keys rounds.py derived from the level (listed in `from_level`) do not count as explicit. Entrance eases
  follow the reel level.
- `transition`: a move name or `"none"` (applies to the cut INTO this segment).
- `camera`: `still` (no camera moves in this shot), `close`, `wide`, `push` (double push), `punch` with `punch: "@word"`.

### Presets that set the motion for you

`project.json` `"preset": "kallaway"` (split engine, `templates/split/README.md` "Presets"): transitions off (hard
cuts), camera `still` inside a thought with a held close/wide switch only on thought breaks, the one analogy beat at
level `simple` (a held close framing, nothing else moves), calm captions (`captions.calm`: fade and rise, at most one accent word per chunk), SFX light with a
soft swish on at most every other top-slot change. Explicit `motion` keys in the project still win. Segment camera
key added for it: `"frame": "close" | "wide"` with `"camera": "still"` (a held framing switch on the cut, nothing else).

## 2. Vocabulary (what the user can say, what it means)

| Say | Name | What it does |
|---|---|---|
| "whip it", "whip pan" | `whip` | the shot pans out under a horizontal motion blur, the next whips in and brakes (4 + 6 frames) |
| "zoom through" | `zoom` | rushes at the lens through the cut, the new shot lands out of it |
| "push in on the new shot" | `push` | a small push on the incoming shot, nothing on the way out |
| "drop it" | `drop` | the shot falls out the bottom, the next drops in from above |
| "circle reveal from my hand" | `iris` | the frame closes to a point (face or hand) and opens on the new shot |
| "flash" | `flash` | a white flash on the cut |
| "smash cut" | `smash` | hard cut with a 1.22x hit and a short flash (impact sound) |
| "rack focus" | `rack` | the speaker comes into focus over 12 frames while the graphic lands |
| "settle" | settle | the shot eases in from 4.5 % bigger on the cut (no visible jump) |
| "punch in" | punch | a quick 6 % hit on the word, then back |
| "wide/close", "two cameras" | reframe | a held framing switch on a phrase start (fake second camera) |
| "handheld" | drift | a few px of smooth seeded drift |
| "make it rise", "draw it on", "stamp", "pop", "drop it in", "track in", "wipe", "smear", "letters" | entrances | `RRM.ENTER.rise / drawOn / stamp / pop / drop / trackIn / wipe / smear / letters / letterStamp / maskPush / blurIn / grow` |
| "behind my head" | behind | the word sits behind the speaker, the live cut-out on top (section 5) |
| "make it simpler" | `level: simple` or `transitions: off` | |
| "show off", "go crazy" | `level: showreel` | |
| "no sound effects" / "more sound" | `sfx: off` / `sfx: full` | |
| "add grain" | `grain: true` | |

## 3. The runtime (motion.js, loaded by every composition as `RRM`)

- **Eases by intent** (`RRM.EASE`): `snap` expo.out (default entrance), `glide` power4.out (big type, panels), `land`
  back.out(1.4) (cards with a small overshoot), `pop` back.out(2.2) (pills, icons), `stamp` power4.out, `drift`
  sine.inOut (idle float), `camera` power2.inOut (focus pushes), `settle` power2.out, `whip` expo.inOut (reveals,
  wipes), `draw` power2.inOut (strokes), `exit` power3.in, `fall` power2.in, `wobble` elastic.out(1,0.45), `push`
  none (camera only, never an entrance). Write the names, not raw curves; `ease_lint` checks entrances.
- **Timing** (`RRM.DUR`): micro 4 f, fast 7 f, base 12 f, slow 24 f, camera 27 f. Exits about 2x faster than entrances.
- **Word anchors** (`RRM.cursor`, `RRM.wordAt`; Python `WordCursor` and `Ctx.cue`): each beat searches the words IN
  ORDER from the previous one, falls back to a relative time when the word is missing, and lands a named lead before
  the word (`visual` 0.04 s, `stamp` 0.03, `push` 0.02, `type` 0.05). Visuals land a frame or two before the word.
- **Entrances** (`RRM.enter(name, tl, el, t, opts)`): `rise`, `blurIn`, `pop` (overshoot), `stamp`, `trackIn` (scaleX,
  never letter-spacing), `wipe`, `drawOn` (SVG `pathLength="1"`), `smear`, `drop` (falls, squashes, wobbles),
  `maskPush` (the line pushes up through an em mask), `letters` (letters rise out of a mask, staggered),
  `letterStamp` (each letter stamps 2 frames apart), `grow` (a caption grows into a headline).
  Exits: `cutOut`, `sink`, `scaleOut`, `fall`, `blurOut`. Hero entrances use at least two of blur, scale, offset.
- **Type**: `RRM.split(el, 'chars'|'words')`, `RRM.mask(el)`, `RRM.fit(el, maxW)` (font-size is a max, only shrinks,
  run after fonts load: `data-mfit="960"` + `RRM.fitAll()`).
- **Physics and polish**: `RRM.shake` (seeded, decaying), `RRM.squash` (overshoot/squash settle), `RRM.flash`,
  `RRM.glow(el)`, `.mv-glow`, `.mv-depth` (layered shadow), `RRM.grain` (opt-in), vignette (`#mvVig`).
- **Keys** (`RRM.keys(tl, sel, fields, rows)`): camera and transitions are planned in Python and applied as one
  `tl.set` per frame. Never overlapping tweens on the same property, so every frame is deterministic and seek-safe.

Layers (split engine): `#mvT` (transitions) wraps paper, speaker, panel and inserts; `#mvCam` (camera) wraps the
speaker plate (`.mv-vid > video`, alone in its div), the behind-head words and the live cut-out. Captions and
persistent overlays (titles, lists) sit outside both, so they never whip or punch. Stylekit: `#mvT > #mvCam > video`.

## 4. Sound on visual events

Every transition and graphic entrance is logged with its time and kind (`work/motion_plan.json` events, plus the
inserts' `cx.event` / `tl.cue`). `engine/motion/mixer.py` places a sound from our own synthesized kit
(`sfxkit.py`: whoosh, whoosh_soft, whoosh_deep, swish, pop, tick, click, stamp, impact, riser, shutter) so its
loudest 10 ms lands ON the event frame.

| sfx | what plays | spacing | level under the voice |
|---|---|---|---|
| `off` | nothing | | |
| `light` (default) | transitions + the first entrance of a new graphic | >= 1.5 s apart, <= 3 per 10 s | 22 dB (transitions 20 dB) |
| `full` | every mapped event | >= 0.18 s apart, <= 14 per 10 s | 20 dB (transitions 18 dB) |

Camera settles, punches and reframes are silent. The loudest 400 ms of the SFX bus never comes closer than 18 dB to
the voice. Muffle windows in `project.json` sound stay clean. A voice-only version is always delivered.

## 5. Behind my head (live cut-out)

```json
"motion": {"behind": [{"text": "FORTITUDE", "at": "@fortitude", "until": "@resilience", "size": 200, "color": "accent"}]}
```

Needs `assets/aroll_matte.webm` (`engine/cutout.py`, background job). The word sits on the camera layer, the cut-out
plays above it only inside the word's window (never across a cut; the layer outlives the window by 3 frames for the
renderer's coverage gate). The head breaks the foot of the word; QA `behind_head` fails when the head hides more than
2 letters. This works because render prep retags HDR footage (section 7).

## 6. QA gates (engine/qa_motion.py, also inside qa.py, styleqa.py, skqa.py)

| check | label in the Room | gate |
|---|---|---|
| `motion_density` | Keeps moving | mean frame diff and % of frames moving (90x160 gray, 15 fps) vs the level target |
| `dead_frames` | No dead stretches | longest still (diff < 2) <= 1.2 s polished / 0.8 s showreel; simple exempt |
| `event_density` | Something new often enough | visual events per second of speech >= 1.2 / 2.0; lists stretches over 1.5 s with none |
| `hdr_alpha` | Cut-outs stay cut out | no HDR-tagged video; alpha videos keep alpha; the render differs from the plate inside each cut-out window |
| `ease_lint` | Entrances snap in | no entrance on a linear or ease-in curve; no opacity-only hero (`data-hero`) entrance |
| `hero_scale` | Hero graphic is big enough | each insert beat's graphic (union of its parts) >= 60 % of the frame width; full-frame B-roll counts |
| `sfx_sync` | Sounds land on the picture | every SFX peaks within +-2 frames of its event; bus >= 18 dB under the voice |
| `behind_head` | Words behind the head stay readable | the head hides <= 2 letters |
| `transition_budget` | Transitions are not overdone | count <= level budget, none inside a cut-out window |
| `motion_strips` | 12 fps review strips | `qa/motion_strip_NN.jpg` around every transition: look at them |

`qa/motion.json` holds the metrics, a per-second motion sparkline, the still stretches and the event list.
A failing density gate is fixed at its cause: give the beat a real move (a graphic that builds, a reframe on a
phrase, a stronger hero), never random wiggle.

## 7. HDR, alpha and the coverage gate (do not skip)

- iPhone footage is HLG (bt2020/arib-std-b67). HyperFrames 0.8.34 then treats the composition as HDR and drops the
  alpha plane of every cut-out layer in the REAL render (lint, check and snapshot all look fine). `engine/hdr.py`
  retags the plate as bt709 (lossless bitstream filter) at assemble and again as render prep for every video the
  composition loads; sparse-keyframe files are re-encoded with a keyframe every 30 frames. Log: `work/hdr_fix.json`.
- Every `<video>` sits alone in its own wrapper div. The renderer inserts each frame image as the video's next
  sibling with the video's z-index, so a timed video next to overlay siblings stacks unpredictably.
- A video layer's `data-duration` is its window + 3 frames (the renderer fails a layer covering under 95 % of it).
- SVG motion blur (`filter:url(#mvMB)`) on a wrapper that contains a `<video>` renders correctly on 0.8.34 (tested).

## 8. Builder brief: the showreel clause (level showreel)

Give this to every builder of a showreel beat, verbatim in spirit, then the hard constraints:

> Build this beat like it is the opening of your motion-design showreel. You are the best motion designer alive and
> this is the shot that proves it. Every cut gets its own move, nothing repeats twice in a row, every graphic lands
> on its word with weight (blur, scale, offset, overshoot), the camera never sits still, and the sound hits on the
> frame. Then make it serve the line: the viewer must understand the idea faster because of the motion, not despite it.

Hard constraints (never broken, at any level): brand tokens only (colours, fonts from brand.json), the safe zone
(nothing readable above y 220 or below y 1470, 35 px sides, right 100 px clear from y 1155), never cover the face,
one hero object per beat, visuals land 1-2 frames before their word, voice always leads (SFX >= 18 dB under), no em
dashes on screen, grain only when asked. For polished: the same craft, at teaching pace (one idea at a time,
density targets above, transitions only on section changes). For simple: cuts, captions, settles, at most one graphic
per idea.
