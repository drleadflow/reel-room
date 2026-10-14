# Split engine (split-deck + style modes)

`compose.py` turns a project into a HyperFrames composition. It is the default **split deck** look and the engine for
style folders (`templates/list-stack`, `templates/motion-editorial`): `project.json` `"style": "<id>"` loads
`templates/<id>/style.py` (DEFAULTS, INSERTS, css, word_cap_top).

## Motion v2 (`motionlayer.py` -> `engine/motion/`)
compose plans the shared motion layer from `project.json` `"motion"` (`references/motion.md`): `#mvT` (transitions)
wraps paper, speaker, panel and inserts; `#mvCam` (camera rig) wraps the speaker plate (`.mv-vid > video`), behind-head
words and the live cut-out. Captions and persistent overlays stay outside both. Plan + events: `work/motion_plan.json`;
`layout_boxes.json` gets `motion` and `motion_events`. render.py / gallery.py mix SFX on the events
(`soundcues.motion_bus`); styleqa appends the motion gates (`engine/qa_motion.py`).

## Split-deck deck camera (`deck.py`, `deck_inserts.py`, Motion v2 phase 3)
On by default for split-deck at polished/showreel (`project.json` `"motion": {"deck": false}` turns it off; another
split-engine style can opt in with `"deck": true`). Every split beat's content sits in `#<beat>cam` (`.dcam`) inside the
beat, so the 960 px panel clip never moves. Per frame (RRM.keys): a slow push through the beat, a glide toward each item
that lands (`deck.focus`), punches on hero hits (`deck.punch`), and a push-through swap (old content leaves up in 4
frames, new rises in 7 under blur) when two split beats meet on a cut with no whole-frame transition. Every frame is
clamped against the MEASURED boxes (compose measures, plans, then writes the page again) so readable content stays in
y 226-952, x 40-1040. Hit words feed the speaker's punches (`cx.deck_accents`); seam captions snap in (pop, 0.2 s).
Deck inserts (same args as the plain ones): `hook_card` (frame-0 readable, line 2 pushes through its mask on its word,
underline draws, leading number stamps), `checklist` (rows stagger in, tick = pop + ring burst + highlight sweep +
progress fill + rolling n/N counter), `table` (loading skeleton rows, rows blur in on their words, a selection bar
follows), `number` (stamp + letters; `"of": 5` adds a step bar), `stat` (odometer roll onto the word, zone meter with a
sliding marker), `name_card` (bigger, bar draws, role smears in), and the new `prompt` (search/prompt bar: focus ring,
types on the words, result chip drops in; args `text, placeholder, focus_at, type_at, type_end, done_at, done`).

## Layouts (`layouts.py`)
`split` (panel on top, speaker under the seam), `full` (+ optional edl `"punch": 1.15`), `card` (paper stage + rounded
speaker card), `stage` (graphics only). Every layout switch, panel/paper/card visibility and speaker transform is a
`tl.set` on the slice's first frame (frame-exact, seek-safe).

## Full-frame overlay layer (`overlay.py`)
`top` items on a `full` segment and project `"overlays"` get `_area = (220, head_top - head_margin)`: the band above
the head box, taken from the per-frame face track (`facetrack.py`, every 3rd frame) mapped through the placement.
Inserts: `name_card` (name + role on its word), `chip` (pill with tick). `cx.extra_boxes` lets an insert report final
states the static measure cannot see (QA uses them).

## Split-deck inserts added
`stat` (label, lead word, giant value on its word with a faint ghost from the cut, tag), `number` gained
`n_at` / `title_at` / `sub_at` / `kicker`. Time anchors also accept `"#cut"` (first frame of a segment).

## Captions (`captions.py`)
`pill` (1-3 words, phrase-aware split with no orphan words) or `word` (one word, sans / serif accent).
No repeats: a caption is hidden while the same words are on screen as fresh type (`captions.repeat_window`, default
2 s; word mode: the word itself; pill mode: every word of the chunk). Hidden chunks stay in layout_boxes.json
(`hidden: true`) so QA still proves the full transcript.

## Deliverables and QA
- `gallery.py <project> <out>`: compose, lint, render (screenshot capture, no 1-frame overlay lag), audio, demo.mp4
  (H.264 ~10 Mbps, < 45 MB), demo-voiceonly.mp4 when SFX/bed are on, loop.mp4 (6 s silent < 4 MB), poster.jpg, styleqa.
- `sound.py`: voice mastered to -14 LUFS (linear gain + true-peak guard, TP <= -2 before AAC), synthesized SFX
  >= 18 dB under, optional lo-fi bed >= 20 dB under, ducked under speech.
- `styleqa.py`: frames / ceil rule, safe zone, face geometry + face-in-render pixel check every 3rd frame, captions
  word-for-word vs words.json + orphans + dashes, switch-on-cut-frame + no blank panels, audio, loop; contact sheets
  `qa/cuts.jpg`, `qa/events.jpg`, `qa/sheet.jpg`, `qa/face_misses.jpg`.

## Presets (`presets.py`): `"preset": "kallaway"`
`project.json` `"preset": "<id>"` is applied by compose before anything else (`presets.apply`): it fills in settings,
the camera per segment and the top-slot plan. Explicit project keys win (dicts merged key by key), and a segment's own
`motion`, `top` and `mode` win over the preset (`"keep_mode": true` keeps a segment exactly as written). Without a
`preset` key nothing changes: the stock split-deck composes byte-identically.

**kallaway** (the split-deck "news deck" look from the research in `our own research notes`, built in our own
style, wording and colours):

| what | how | where |
|---|---|---|
| split held for most of the reel | every segment `mode: "split"` (top slot 50 %, speaker plate below) except the analogy beat | `presets._layout` |
| a new top-slot picture about every 1.0 s (0.8 to 1.4) | free split stretches are chopped into pictures, boundaries snapped to word starts; each picture gets a slow push (even) or a lateral drift (odd) and hard-cuts in (no deck swap) | `feed.py` |
| B-roll feeder | `assets/broll/broll.json` (`items`: `src`, optional `word` + `seg` pin, `media_start`, `kind: "screen"`, `arrow`), else every media file in `assets/broll/` sorted; runs out -> kit cards (the window's key word on a paper / ink / accent card) | `feed.sources`, `feed.plan` |
| topic banner on frame 1 | project `"banner": "GET IN SHAPE FAST"` (3 to 5 words) or `{"text", "dur": 2.5}`: label-pill tag, readable on frame 1, lifts away | `kallaway.topic_banner` |
| receipt-proof beat | segment `"purpose": "proof", "proof": {"src", "row": [x,y,w,h] img px, "spot_at", "value": {"value", "at", "label", "prefix"}, "arrow": {"to", "from", "at", "label"}}`: framed screen, kit spotlight on the row, kit odometer on the key number, kit arrow on the noun | `kallaway.proof_screen` |
| arrow on the spoken noun over screens | `arrow` on a proof or on a `kind: "screen"` feed item (kit annotation-arrow, `at: "@noun"`) | `feed._arrow` |
| one full-frame analogy beat | segment `"purpose": "analogy"` (or `"layout": "full"`): full frame, the calm beat (level `simple`, camera still with a held close framing on the cut into it, no graphics); warns if there are more | `presets._camera` |
| head bubble | segment `"bubble": {"at", "back", "corner", "size", "label", "behind": {"insert": "diagram", "args": {"title", "hub", "nodes": [{"text", "at"}], "pulse"}}}`; a full-frame overlay from the segment start to its end (one shot) | `kallaway.head_bubble` |
| keyword comment CTA at the end | project `"cta": {"keyword", "from": "@word", "type_at", "post", "dm_at": "#seg", "dm_text", "link_text", "link_sub"}` (`dm_at` on a cut lands the DM on that cut) | `kallaway.cta` |

the house rules ride on top: captions `calm` (pill chunks of up to 4 words fade and rise 12 px over 8 frames, no pop, no stamp; at most
one accent word per chunk in the brand highlight, accents default to the spoken numbers); `motion.transitions: "off"`
(hard cuts); camera `still` inside a thought and a held close/wide framing switch only on thought breaks (a cut after a
sentence end or a layout change, engine `motion.frame`); SFX `light` (a soft swish on at most every other top-slot
change, the mixer keeps them 20-22 dB under the voice, never closer than 18); no grain. The deck camera skips feed
pictures. `layout_boxes.json` `preset` reports the feed (`pictures`, `broll`, `cards`, `intervals`, `mean`).
Captions break only where the speaker changes (feed changes are not caption breaks, `presets.caption_slices`).
Head-bubble windows are masked for the face QA (`report.pip_mask`): the face is in the bubble, not on the plate.
