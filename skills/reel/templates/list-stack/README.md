# List Stack

One take of you, full frame. A title and a numbered list sit in the free band above your head and fill in, item by
item, exactly as you say each one. Captions ride in a clean pill at chest height. The empty slots are the open loop;
the finished list is the screenshot people save.

Runs on the split engine (`templates/split/compose.py`); this folder only adds the list overlay and its CSS.

## Setup in a project

`project.json`
```json
{"style": "list-stack",
 "overlays": [{"insert": "list_stack", "args": {
   "title": {"n": "5", "l1": "THINGS I'D DO", "l2": "to get in shape fast", "at": "@5"}, "n": 5,
   "hide": [{"from": "#cred1", "until": "#n1a"}],
   "items": [
     {"on": "#n1a", "label": "Blood work", "at": "@blood",
      "detail": [{"text": "full panel", "at": "@full"}, {"text": "+ fasting insulin", "at": "@fasting"}],
      "tag": {"text": "over 7 = insulin resistance", "at": "@7"}},
     {"on": "#n2", "label": "A deadline", "at": "@deadline"}]}}],
 "gallery": {"sfx": true, "loop_at": 11.6, "poster_at": 24.6}}
```
`edl.json`: every segment `"mode": "full"`, no `top`. Give same-framing jump cuts a framing change with
`"punch": 1.15` (css punch-in; the origin sits above the face so the head grows downward and the list keeps its room).

| item key | meaning |
|---|---|
| `on` | when the row appears and becomes ACTIVE (emphasis colour). `"#n1a"` = ON the first frame of cut `n1a`. The previous row turns calm on the same frame |
| `label`, `at` | the item text and the word it lands on (it pushes up through a mask on the word) |
| `detail` | inline detail after the label, parts land on their own words |
| `tag` | accent pill; it takes the detail's place in the row (no row growth) |
| `hide` | windows where another topic is on (the list is off, back on at `until`) |
| `clear_at` | when the list idea ends (0.3 s fade); default: end of video |
| `empty` | `"hidden"` (default, rows appear as spoken) or `"slots"` (faint empty rows from the start) |
| `title.at` | the spoken count: the big number pulses and one progress tick per item pops in |
| `transitions` | default `true`: a cut where an item lands, or where the list leaves / returns, counts as a section change, so the engine motion layer may give it a transition (level budget; moves narrowed to zoom-through / circle reveal unless project.json motion.transitions names its own; the list, the hero and captions sit outside it) |

Time anchors: `"@word"`, `"@word:2"`, `"@word+0.2"`, `"#cut"`, or seconds.

## List rules (fixed scaffold)

Row slots are planned once: every row has the same height (1.44 x the label size) and gap, so every number glyph keeps
one position and size for the whole video. Rows never move between slots: every row motion is centred on the row's own
number badge, so the glyph stays put (QA `list_rules` measures it). compose writes the plan to `P/work/list.json`
(`{items:[{n,t_in,box,row}], clear_at, scaffold, hidden}`; `scaffold` is true only with `empty: "slots"`, when every
number is on screen from the first reveal) for `engine/qa.py` `list_rules`; `gallery.py` copies it to `<out>/list.json`.

## Motion (v2 phase 3, built in)

| moment | what moves |
|---|---|
| list in (frame 0, and again when it returns after a `hide`) | the big number stamps in (scale + blur), the title lines push up through masks |
| `title.at` (the spoken count) | the number pulses, one progress tick per item pops in under the title |
| item `on` (its cut) | the number badge stamps, the card grows out of the badge, the accent fill wipes across from the badge (expo.inOut), a light sheen sweeps once, the row pushes 2.5 % about its badge, its progress tick fills |
| label / detail / tag words | the label pushes up through a mask; details blur in from the left; the tag pops (back.out) as the details leave fast |
| the next item lands | the finished row's fill clears, its card compresses to 84 % height about the badge, text dims to ink and shrinks 7 %, its tick turns ink |
| `clear_at` | rows lift out bottom-up with blur, then the masthead |

Camera (settle, punch on emphasis words, reframes) and section transitions come from the engine motion layer
(`references/motion.md`). Give the project `captions.accent` words so the punches land on the items and numbers.

## Placement and safety

The band is `220 px` to `head_top - head_margin`, where `head_top` is the highest point of the head box (cap/hair)
over the WHOLE video, from the per-frame face track (`split/facetrack.py`) mapped through every punch-in. The label
size steps down until all N rows fit that band; compose warns if they cannot.

## Build

```
PY SK/templates/split/facetrack.py P          # once per A-roll
PY SK/templates/split/gallery.py P OUT         # compose, lint, render, master audio, demo/loop/poster, styleqa
```
Sound: dry voice by default; `gallery.sfx` adds a soft tick on fills only (22 dB under the voice). Graphic events use
the sound kinds pop (number stamps), click (text), tick (progress, details) and whoosh (highlight sweep, list clears).
Renders on a shared machine: `PRODUCER_LOW_MEMORY_MODE=true` streams frames instead of ~8.6 GB of temp PNGs.
