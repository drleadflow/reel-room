# Motion Editorial

A paper-white motion-graphics stage on top, you in a rounded card below, one-word captions that swap between a bold
sans and an italic serif accent. Graphics-only beats (paper only, your voice keeps running) and full close-ups sit in
between. One hero graphic per beat, a change every 2 to 3 s, every element lands on its spoken word.

Runs on the split engine (`templates/split/compose.py`); `style.py` adds the inserts, caption placement and CSS.
Fonts: brand display (bold sans), Instrument Serif italic (accent), JetBrains Mono (labels), fetched once and cached.

## Layouts (edl `mode` or project beat `layout`)

| layout | what you see |
|---|---|
| `card` | paper stage 220 to 912 px, caption word just above the card, speaker card from y 1040 (radius 72, face centred at y 1372) |
| `stage` | paper only, graphic 220 to 1170, caption word below it |
| `full` | full-frame close-up; `top` items are placed above the head box; caption word in a dark pill at chest |

Card geometry: `project.json` `"card": {"top", "inset", "radius", "face_y", "scale", "caption_band", "anchor"}`.
`anchor: [x, y]` (aroll px) frames every card segment on that point instead of each segment's face: a fixed, steady
shot, e.g. a wide card of the speaker and his whiteboard (`scale` 0.95 fills the card width). An edl `punch` still
multiplies the scale on one segment (a small 1.06 step where a jump cut needs a visible change).

## Inserts

| insert | args |
|---|---|
| `kinetic` | `lines: [{text, font: sans/serif/mono, size, color: ink/accent/gold/soft, at, enter: rise/pop/slam/slide/cut, sfx}]`, `swoosh: {line, at, w}` |
| `numeral` | `n, label, size, at, circle_at, title, title_at, title_font` (hand-drawn circle draws around the numeral) |
| `cred_stack` | `label, items: [{text, at, font}]` (01 / 02 / 03 lines) |
| `lab_report` | `title, rows: [{test, note, at}], enter_sfx` (paper sheet, rows land on words) |
| `lab_focus` | `test, note, prev, prev_note, line, circle_at` (one line magnified, circled on its word) |
| `big_stat` | `label, label_style: serif, pre, pre_at, value, at, size, tag: {text, at}` |
| `gauge` | `label, left, right, needle: {from, to, at}, mark, mark_at, r` |
| `tiles` | `heading: {text, at, font}, items: [{icon: plate/dumbbell/drop/flask/calendar/heart, label, at, tone}], size` |
| `cal_flip` | `kicker, page1: {top, big, font, small}, page2: {...}, flip_at` (page flips, circle draws) |
| `media_stack` | `media` layout only (hook.py). `full: {src, media_start or track_t0, pan, push, shake_at}` or `top: {...}` + `bottom: {...} or "dark"` with `slide_at, slide_from, shrink_top, steps: [[anchor, scale, ox, oy]]`, `labels: [{text, panel, at}]`, `cap_y` (caption top on this plate). `track_t0`: the clip is a cut-time track starting at that cut, so it continues across beats; `pan: [[cut_t, src_y]]` moves the window over the clip |
| `title_card` | the hook title on a paper card (hook.py): `l1, l2, y, max, exit`; use as a project overlay (`"overlays": [{"insert": "title_card", "from": 0.35, "until": 4.95}]`) so it holds across beats; slams in on `from` |
| `cycle_chart` | step-by-step drawn curve (chart.py): baseline, V dip, recovery, up/down branch, brackets, `YOU?` glide, 4 numbered slots (`axis: row` list plan for qa list_rules); `mode: unbreakable` stretches the baseline. Every step is an anchor in `steps` |

Fonts: `font_setup(brand)` uses the brand's `fonts.serif` (default Instrument Serif) for the italic accent and
`fonts.mono` for labels, so a project `brand.json` can swap them (a test reel uses Playfair Display).

Hand-drawn strokes are seeded paths (`_scribble_path`), so every render is identical.

## Captions

`"captions": {"mode": "word", "accent": [words...]}`: one word at a time, hard swap (no pop). Accent words switch to
the italic serif in the accent colour; without a list, numbers and words of 7+ letters are accents. Trailing commas
and periods are dropped on screen; the words themselves are exactly `words.json`.

## Sound

`"gallery": {"sfx": true, "bed": true, "plan": {"sfx": {"only": [...], "min_gap": 1.0, "max_per_10s": 3, "under_db": 20}, "bed": {"under_db": 22}}}`.
SFX (whoosh, pop, thud, scribble, flip, click) and the lo-fi bed are synthesized in `split/sound.py` (no samples, no
licences). Inserts register their moments with `cx.event`; the plan picks about 2 per 10 s. A voice-only demo is
always written next to the mixed one.

## Example

`<your-work-folder>` (edl.json + project.json) is the 35 s gallery demo.
