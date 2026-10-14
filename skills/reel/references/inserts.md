# Inserts reference (split-deck template)

This is the one file to read before filling `top` in `edl.json` or `beats` in `project.json`. Everything is a small
function: `(args, brand) -> html + entrance tweens`. Colours and fonts come only from `~/.reel-room/brand.json`.

## Beat purpose (decide this first)

Every storyboard beat carries a `purpose`, one of: `promise`, `explanation`, `contrast`, `proof`, `demonstration`,
`payoff`, `cta`. Pick the visual from the purpose, never from the asset folder.

- Never add a visual just because an asset exists. Presenter only (no insert) is a valid choice and often the best
  one for a personal line or a punchline.
- One focus per beat. Decide what the viewer notices first. Headline, card, captions and a big gesture never compete.
- `proof` shows the proof of that claim (the real result, screenshot, lab line), readable, then it goes away. No
  decoration or loose B-roll over a claim line.
- `demonstration` shows the action being done. `contrast` shows both sides. `promise` and `payoff` are often big text
  or the presenter. `cta` ends on readable proof first, then the call to action, all inside the safe zone.
- Vary layouts at real turns in the speech, not on a timer. Several beats in a row with the same layout: change one.
- Bring a visual in as its idea is spoken, hold it long enough to read, clear it when the idea ends.
- Generated visuals: write `visual_intent` (one sentence) into the beat first, `references/visual-prompts.md`.

## Placement and motion (check the real footage, every beat)

- Map the moving face, big gestures, captions, any headline and the frame edges across the WHOLE interval of the
  beat, not just its first frame. Pick the largest readable placement in the space left. Re-check when another
  element clears, and never copy the previous shot's positions without checking.
- Nothing fits: simplify before shrinking text. Drop a redundant label, crop or resize the asset, reframe the speaker
  down uniformly to make headroom, or use a short split. Use the cutout for depth only when its edges are clean. A
  short full-screen proof shot may cover the face only when the evidence must be readable.
- Typography moments (big keyword, small connecting words, revealed in spoken order) hide the caption while they
  show the same words. Never just repeat the caption.
- Motion follows meaning: entrances ease in, gentle push or pull across a whole phrase, mix push, pull and static.
  Reframing changes land on cuts or phrase starts (the motion planner places them). Entrance sounds follow
  `motion.sfx` (light by default: only the first entrance of a new graphic).
- Lock fonts by rendering the real words at full size before choosing. Font names and rendered results differ.

## Where an insert goes

Every cut must land on a layout change (`split` <-> `full`) or a new top-panel insert. `compose.py` prints
`WARN jump cut A -> B ...` for each cut that does neither. `full` segments have no top panel (no inserts).

Layouts (`mode` / beat `layout`): `split`, `full`, plus the styles' `card` and `stage`, and `media` (full-frame B-roll
plate drawn by the beat, speaker hidden, captions in a dark pill at the beat's `cap_y`; motion-editorial `media_stack`).
Framing changes that count as a new shot on a jump cut: edl `"punch"` (full: zoom around the face, `"punch_at":[x,y]`
puts the face centre there; card: multiplies `card.scale`). An insert that changes the picture exactly on a cut frame
registers it with `cx.cut_change(t)` (e.g. a B-roll step-in on a `"#seg"` anchor), so compose does not warn there.

### `top` on an edl segment (edl.json)

```json
{"id":"n1a","mode":"split","top":{"insert":"number","args":{"n":"1","title":"Blood work","sub":"start with a full panel"}}}
```

| `top` value | Meaning |
|---|---|
| `null` / missing | empty panel (use only with `mode:"full"`) |
| `{"insert": "<name>", "args": {...}}` | one insert |
| `[ {insert,args}, {insert,args} ]` | several inserts share the panel (hook card + polaroids) |
| `"<name>"` | shorthand for an insert with no args |
| `"same"` | keep the previous beat running across this cut (extends it; no new entrance) |

An insert that is the only thing in the panel is centred vertically in the visible area (y 220-940) unless you pass
`y`. With 2+ inserts each keeps its own default position (hook card at y 250, polaroids at y 580).

### `beats` in project.json (change the panel in the middle of a segment)

```json
"beats": [
  {"at_word": "someone", "seg": "n5a", "layout": "split", "insert": "video", "args": {"src": "assets/broll/partner.mp4"}},
  {"at_src": {"seg": "n5b", "t": 272.1}, "until_word": "together", "layout": "split",
   "items": [{"insert": "collage", "args": {"srcs": ["assets/broll/a.mp4","assets/broll/b.mp4","assets/broll/c.mp4","assets/broll/d.mp4"]}}]}
]
```

| Key | Meaning |
|---|---|
| `at_word` (+ `seg`) | start at the first spoken word matching this text inside segment `seg` (`"gains:2"` = 2nd occurrence) |
| `at_src: {seg, t}` | start at source-clip time `t` seconds inside segment `seg` (as in edl `in`/`out`) |
| `at` | start at cut time in seconds |
| `until` / `until_word` / `dur` | end (cut seconds / spoken word / length). Default: end of the segment |
| `layout` | `"split"` (default) or `"full"` |
| `insert` + `args`, or `items: [...]` | what to show; same shape as `top` |

A beat overrides whatever the edl `top` shows for its time range; the rest of the segment keeps its own insert.

## Timing anchors (inside `args`)

| Value | Meaning |
|---|---|
| number `0.8` | seconds after the beat starts |
| `"@word"` | the moment that word is spoken, first match inside the beat (exact word first, then prefix) |
| `"@word:2"` | 2nd occurrence |
| `"@word+0.3"` / `"@word-0.2"` | offset from that word |
| `null` | insert's default timing |
| `false` | (checklist `ticks`, table `reveal`) never in this beat |

Entrances only: 0.25-0.4 s rises, polaroids land with `back.out` 0.32 s. At most one change per sentence.
At motion level polished/showreel the engine swaps plain power eases on entrances for the snap (expo.out) and fixes
any entrance on a linear or ease-in curve (`references/motion.md`). In a new insert use the motion vocabulary
(`RRM.enter('rise'|'stamp'|'pop'|'drawOn'|'letters'|...)`) and the ordered word cursor (`cx.cue("@word", beat,
after=prev_t, lead="visual")`): visuals land 1-2 frames before their word, each cue searches after the previous one.

## Inserts

Aliases in parentheses. Paths are relative to the project folder. `y` is the top of the block in frame pixels.

### `hook_card` (`hook`)
Accent card, 2 ALL-CAPS lines, auto-shrinks to fit 1010 px wide. Static from the first frame unless `enter` is set.

| arg | type | default | example |
|---|---|---|---|
| `l1`, `l2` | string | `project.json` `hook.l1` / `hook.l2` | `"Your fastest shred"` |
| `y` | int | 250 (with polaroids) / centred (alone) | `250` |
| `max` | int | 930 | text width cap |
| `enter` | `true` / time | none (static) | `0.2` |

### `polaroids` (`polaroid`, `polaroid_row`)
Row of 1-4 white-frame photo pairs, handwritten caption (brand hand font), result in alert colour, slight tilt.

| arg | type | default | example |
|---|---|---|---|
| `items` | list of `{img,name,result}` | required | `{"img":"assets/broll/pol_frank.jpg","name":"Dr. Frank","result":"−62 lbs"}` |
| `at` | list of anchors | 0.4 s + 0.45 s each | `["@shape","@humanly","@things"]` |
| `y` | int | 580 | `580` |
| `rot`, `dy` | lists | `[-4,-1.5,3.5,-2.5]`, `[10,-8,12,0]` | tilt degrees, vertical offsets |

Use the real minus sign (−), never an em dash.

### `number` (`number_card`)
Huge numeral in accent + title + optional sub line.

| arg | type | default | example |
|---|---|---|---|
| `n` | string | required | `"1"` |
| `title` | string | required (auto-fits 960 px) | `"Blood work"` |
| `sub` | string | none | `"start with a full panel"` |
| `y` | int | centred | `300` |

### `table` (`data_table`)
Lab-report card, rows reveal on words, one row can be highlighted, one tag.

| arg | type | default | example |
|---|---|---|---|
| `rows` | list of `[col1, col2]` | required | `[["CBC","Blood counts"],["Fasting insulin","Insulin resistance"]]` |
| `cols` | 2 strings | `["TEST","WHAT IT SHOWS"]` | `["TEST","MEANING"]` |
| `reveal` | anchors per row | 0.2 s + 0.25 s each | `["@a","@panel",false]` (`false` = row stays blank here) |
| `instant` | int | 0 | first N rows already there (use when the table continues after a cut) |
| `highlight` | `{row, at}` | none | `{"row":4,"at":"@insulin"}` |
| `tag` | `{text, row, at}` | none | `{"text":"Often skipped","row":4,"at":"@often"}` |
| `enter` | bool | true | `false` when continuing |
| `y` | int | centred | |

### `calendar` (`calendar_grid`)
Numbered week grid with chosen weeks and result pills.

| arg | type | default | example |
|---|---|---|---|
| `title` | string | none | `"Pick a deadline"` |
| `n`, `cols` | int | 16, 8 | |
| `select` | list `{n, at, soft?}` | none | `[{"n":8,"at":"@8"},{"n":16,"at":"@16","soft":true}]` |
| `pills` | list `{text, kind, at, strike_at?}` | none | `{"text":"3 years","kind":"bad","at":"@3","strike_at":"@years"}` (`kind`: `good`/`bad`) |
| `y` | int | centred | |

### `checklist`
Card with a title and rows; ticks land one by one.

| arg | type | default | example |
|---|---|---|---|
| `title` | string | "" | `"Zero friction"` |
| `items` | list of strings | required | `["Wake up","Plan mapped out"]` |
| `ticks` | anchors per row | 0.4 s + 0.4 s each | `["@wake","@plan",false]` |
| `instant` | list of row indexes | [] | `[0,1,2,3]` already ticked |
| `enter` | bool | true | |
| `y` | int | centred | |

### `two_path` (`two_path_card`)
Two (or more) "condition → result" rows.

| arg | type | default | example |
|---|---|---|---|
| `rows` | list `{cond, result, at?, tone?}` | required | `{"cond":"You don't","result":"Meal prep company","at":"@doesn't"}` |
| `y` | int | centred | |

### `strike_pill`
Pill whose text gets struck through, with an optional red line under it.

| arg | type | default | example |
|---|---|---|---|
| `text` | string | required | `"Uber Eats every day"` |
| `strike_at` | anchor | 0.9 s | `"@every"` |
| `sub` | string | none | `"not a meal plan"` |
| `at` | anchor | beat start | |

### `cta` (`cta_card`)
Accent card with 2 lines plus a small line.

| arg | type | default | example |
|---|---|---|---|
| `l1`, `l2` | string | required | `"TAG YOUR"`, `"GYM BUDDY"` |
| `emoji` | string | none | `"👇"` |
| `small` | string | none | `"the one you want to make gains with"` |

### `image`
Still photo with a Ken Burns push (6 %).

| arg | type | default | example |
|---|---|---|---|
| `src` | path | required | `"assets/broll/mealprep.png"` |
| `box` | `[x,y,w,h]` | `[0,220,1080,720]` | `[0,0,1080,960]` for a photo that already has its own top band |
| `fit` | `cover`/`contain` | cover | `contain` for screenshots with text |
| `pill` | `{a, b, at}` | none | `{"a":"Cook?","b":"MEAL PREP.","at":"@meal"}` (b is accent coloured) |
| `kenburns` | bool | true | |

### `flip` (`before_after`)
Stack of contained images; flips to the next with a 0.34 s turn.

| arg | type | default | example |
|---|---|---|---|
| `srcs` | list of paths | required | `["assets/broll/ba1.png","assets/broll/ba2.png"]` |
| `at` | list of anchors (first = `null`) | evenly spread | `[null,0.75,1.5]` |
| `box` | `[x,y,w,h]` | `[0,220,1080,720]` | |

### `video` (`broll`)
Full-panel B-roll (1080x960, cover). Baked-in black bars are detected and cropped away.

| arg | type | default | example |
|---|---|---|---|
| `src` | path | required | `"assets/broll/doc.mp4"` |
| `media_start` | seconds | 0 | `2.5` |
| `box` | `[x,y,w,h]` | `[0,0,1080,960]` | |
| `autocrop` | bool | true | `false` for very dark clips |

### `collage` (`collage2x2`)
2x2 grid of muted videos.

| arg | type | default | example |
|---|---|---|---|
| `srcs` | 4 paths | required | |
| `media_start` | list of seconds | zeros | `[0,2,0,3]` |
| `box` | `[x,y,w,h]` | `[0,200,1080,760]` | |
| `gap` | px | 4 | |

## List rules (any style that shows a numbered list)

- Fixed scaffold: numbers sit at the same position, size and scale through every reveal. Nothing in the list moves
  when an item appears or grows (reserve the row height up front).
- Reveal each item as it is spoken. Highlight the active item; earlier items stay but step back.
- Even row spacing by rendered text height, the group compact and inside the safe zone.
- Clear the list before the next topic starts.
- Prove it from the render: the style writes `P/work/list.json` and `qa.py` runs `list_rules` (shape in
  `engine/qa_extra.py`): `{"items":[{"n":1,"t_in":13.6,"box":[x,y,w,h],"row":[x,y,w,h]}],"clear_at":35.0,"scaffold":true}`.
  `box` is the number glyph, `row` the item row, both in final-frame pixels, times in cut seconds. No file: the check
  says "not applicable".

## Captions (not an insert)

Built from `words.json`: 1-3 words, no animation, never spanning a cut. Split: dark pill on the seam. Full: dark pill
at chest height, always below the chin. Option in `project.json` or `brand.json`:

```json
"captions": {"full_style": "pill", "max_words": 3, "max_chars": 26}
```
`full_style`: `pill` (default, dark rgba(12,12,15,.82)), `shadow` (white text with shadow, only over dark backgrounds),
`scrim` (soft dark gradient). `layout_boxes.json` carries `style` on every caption box so QA can check contrast.

## Copy-paste examples

### 1. Hook card + polaroids (first segment)
```json
{"id":"hook","mode":"split","top":[
  {"insert":"hook_card","args":{"l1":"Your fastest shred","l2":"Starts with labs"}},
  {"insert":"polaroids","args":{"at":["@shape","@humanly","@things"],"items":[
    {"img":"assets/broll/pol_frank.jpg","name":"Dr. Frank","result":"−62 lbs"},
    {"img":"assets/broll/pol_george.jpg","name":"Dr. George","result":"−31 lbs"},
    {"img":"assets/broll/pol_gino.jpg","name":"Dr. Gino","result":"−29 lbs"}]}}]}
```

### 2. Table with a highlighted row and a tag (continues after a cut)
```json
{"id":"n1d","mode":"split","top":{"insert":"table","args":{
  "rows":[["CBC","Blood counts"],["CMP","Kidneys, liver, sugar"],["Fasting insulin","Insulin resistance"]],
  "instant":2,"enter":false,"reveal":[null,null,"@fasting"],
  "highlight":{"row":2,"at":"@insulin"},
  "tag":{"text":"Often skipped","row":2,"at":"@often"}}}}
```

### 3. Collage, then a different collage on a later word (mid-segment beat)
```json
{"id":"n5b","mode":"split","top":{"insert":"collage","args":{
  "srcs":["assets/broll/group.mp4","assets/broll/gym.mp4","assets/broll/partner.mp4","assets/broll/group.mp4"],
  "media_start":[0,0,0,3]}}}
```
```json
"beats":[{"at_word":"gains","seg":"n5b","layout":"split","insert":"collage","args":{
  "srcs":["assets/broll/gym.mp4","assets/broll/partner.mp4","assets/broll/group.mp4","assets/broll/gym.mp4"],
  "media_start":[4,2,6,1]}}]
```

## Commands

```
python templates/split/compose.py <project>        # index.html + layout_boxes.json (prints WARN lines)
python templates/split/render.py lint <project>    # short lint; runs: npx --yes hyperframes@0.8.34 lint (from the project folder)
python templates/split/render.py <project>         # compose, lint, render renders/<slug>-vN.mp4 (one progress line)
python templates/split/render.py <project> --safe  # draft with the safe-zone guide painted on
python templates/split/render.py snap <project> 4.6 12 30   # stills at cut times -> <project>/snapshots/
```
