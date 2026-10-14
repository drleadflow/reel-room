# Carousel Slide-up

A 10-14 s condensed cut: one reframed shot of the speaker (face high), a serif title for the whole reel, and cream
carousel cards that rise from the bottom one after another on their words (the previous card tilts back and falls away
as the next rises). No captions (title and cards carry the text). The reference is music-only; this version keeps the voice.

Build: `PY SK/templates/stylekit/build.py <project> --out <dir>` with `"template": "carousel-slideup"`.

## The cut (`cut.py`)

Re-cuts chosen takes from the FULL-RES source (crisp after the reframe), exact frame counts, 20 ms fade-in / 30 ms
fade-out at each join, an optional silent tail taken from the source (room tone, not digital silence) and an optional
punch-in per piece (anchored on the face so the face never moves into the cards). Writes `assets/aroll.mp4` (graded),
`assets/voice.wav` (untouched), new `words.json` / `segments.json` and `work/facetrack.json`. Cut points must be in
measured silence: pick them from the energy (`splice.py env`) or existing segment boundaries.

## project.json `style_cfg`

```json
{
 "cut": {"source": "/abs/IMG_6545.MOV", "offset": 5.0, "from_project": "/abs/sample",
         "crop": {"w": 1664, "h": 2958, "x": 288, "y": 882, "punch_anchor_y": 0.37},
         "grade": {"lift": 0.025, "gamma": 0.92, "warm": 0.022, "sat": 1.05, "green": 0.99},
         "pieces": [{"seg": "hook"}, {"seg": "n1a"}, {"seg": "n1b", "to": 16.80, "punch": 1.06}, {"seg": "n2", "tail": 18}]},
 "title": {"l1": "5 things I'd do", "l2": "to get in shape", "accent": "fast", "y": 232,
           "l2_at": "@get", "accent_at": "@fast", "num_at": "@5"},
 "cards": [
  {"at": "seg:n1a", "eyebrow": "NO. 01", "of": 5, "title": "Blood work", "copy": "Full comprehensive panel", "copy_at": "@full",
   "rows": [["Glucose", 46, "@comprehensive"], ["Fasting insulin", 72, "@panel"]], "footer": "YOUR NAME"},
  {"at": "seg:n2", "eyebrow": "NO. 02", "of": 5, "title": "A deadline", "weeks": {"n": 12, "pick": 12, "at": "@deadline"}}
 ],
 "loop": {"t0": 4.3}, "poster": {"t": 7.2}
}
```

`offset` maps the from-project's source times to `source` (the sample clip is IMG_6545.MOV from 5.0 s; measured by
audio cross-correlation). Crop is a 9:16 window in source pixels; aim the face around y 700 of 1920 so the title fits
above the cap and the card (y 918-1446) sits under the chin. Card slots: eyebrow, page `i / of`, big title (auto-fit),
optional copy line, optional mini rows (revealed on words), optional week grid (pick lands on a word), footer wordmark.
Sound: one soft swish per card, a quiet pop on the accent word and on the pick. No music.

## Motion (v2 phase 3, built in)

| moment | what moves |
|---|---|
| frame 0 | title line 1 stamps in (already faint on frame 0: scale 1.16 + blur to sharp) |
| `l2_at` / `accent_at` / `num_at` | line 2 pushes up on its word; the accent word slams in (2.3x, -9 deg, blur); a leading number in line 1 pulses in the accent colour when spoken |
| card `at` | the card rises with momentum: tilted back in 3D (rotationX -26), motion blur, a small overshoot (back.out 1.4), then floats (x / rotation sine) |
| the next card | the previous card tilts back in 3D (rotationX 58, z -220) and falls away while the new one rises |
| rows (`rows[][2]` words) | the row lights, its bar fills (expo.out) and its value counts up from 0 on the word |
| week grid | weeks tick off one by one from the card's arrival up to the pick; the pick stamps on its word, the flag pops |
| whole reel | the card stack is its own depth plane (`#ccStack`): it follows the engine camera at 35 % (motion parallax), so the shot moves behind the cards |

Micro events (rows, ticks, title words) are logged with their own small regions and kinds (fill, tick, type, stamp),
so QA checks that each one changes on its frame, and only card entrances count as hero beats.
