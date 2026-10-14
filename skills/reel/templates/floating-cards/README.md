# Floating Cards

Bright, polished full-frame talking head. Frosted UI cards fly in around the head in real 3D on their words, land
with a small overshoot and a contact shadow, float while they hold, and stack, fan or dock as the topic moves.
Struck-out items get a red strike and tumble away. One big word rises letter by letter BEHIND the head (live
cut-out). A step HUD counts the list. Single-word glow captions at chest height. Motion v2 camera on the speaker.

Build: `PY SK/templates/stylekit/build.py <project> --out <dir>` with `"template": "floating-cards"` in project.json.
Needs `assets/aroll.mp4`, `assets/aroll_matte.webm` (cutout.py), `words.json`, `segments.json`, `edl.json`,
`work/facetrack.json` (`stylekit/skface.py assets/aroll.mp4 work/facetrack.json`). Colours and fonts: brand.json
(`accent` = cards/word/HUD, `highlight` = glow/gold, `alert` = strike, `fonts.serif` = title accent line).

Code: `compose.py` (timeline, title, HUD, captions, base plate), `fc_cards.py` (card markup + 3D motion),
`fc_behind.py` (live behind-head word + its graded cut-out clip), `fc_style.py` (CSS).

## project.json `style_cfg`

```json
{
 "grade": {"lift": 0.03, "gamma": 0.9, "warm": 0.02, "sat": 1.05, "green": 0.98},
 "title": {"l1": "5 things I'd do", "l2": "to get in shape", "l3": "fast.", "y": 262, "until": "seg:cred1",
           "l1_at": 0.0, "l2_at": "@get", "l3_at": "@fast"},
 "hud": {"n": 5, "at": "@5", "y": 600, "dock_at": "seg:cred1", "dock_y": 236, "steps": [{"n": 1, "at": "@1,"}]},
 "behind": [{"text": "BLOOD", "at": "@blood", "until": "@panel-0.12", "y": 690, "size": 292, "sfx": "thump"}],
 "cards": [
  {"at": "@physician", "until": "seg:n1a", "icon": "stethoscope", "title": "Physician", "sub": "Medical doctor",
   "x": 56, "y": 470, "moves": [{"at": "@before", "dx": -16, "dy": -130, "rot": -5, "scale": 0.86, "what": "stacks"}]},
  {"type": "chip", "at": "@ozempic", "icon": "syringe", "text": "Ozempic", "x": 640, "y": 600, "strike_at": "@was"},
  {"type": "panel", "at": "@panel", "until": "seg:n1d", "title": "Lab panel", "sub": "Metabolic health",
   "rows": [["Glucose", 62, "@tells"]], "ul_at": "@metabolic",
   "slot": {"label": "Fasting insulin", "at": "@sure", "fill_at": "@fasting"}, "x": 60, "y": 300},
  {"type": "status", "at": "@insulin>n1d", "until": "seg:n2", "eyebrow": "Fasting insulin", "value": "< 7",
   "value_at": "@7,", "unit": "µIU/mL target", "row": "Over 7: insulin resistance", "row_at": "@resistance",
   "pulse_at": ["@resistance>n1e"], "x": "center", "y": 300,
   "moves": [{"at": "@dictate", "dx": -262, "dy": -50, "scale": 0.6, "what": "docks"}]},
  {"type": "week", "at": "@deadline", "until": "end", "n": "12", "flag": "Deadline", "x": "center", "y": 470, "from": "front"}
 ],
 "loop": {"t0": 9.4}, "poster": {"t": 15.0}
}
```

- Card types: `icon` (default: glyph tile + title + sub), `panel` (title + rows `[name, bar %, "@word"?]`: a row with a
  word fills and ticks on it; optional `slot` = a dashed empty row that opens on `at` and fills on `fill_at`;
  `ul_at` draws a gold underline under the sub), `status` (big value with a gold glow; `value_at` stamps the value
  letter by letter; `row` lands on `row_at`; `pulse_at` pulses it), `week` (calendar glyph + number, optional `flag`),
  `chip` (pill, optional `icon`).
- Icons (simple glyphs, no brands): stethoscope, clipboard, tube, drop, fork, dumbbell, calendar, gauge, spark, syringe.
- `at` / `until`: `"@word"`, `"@word:2"`, `"@word+0.2"`, `"@word>segid"` (first match inside that segment),
  `"seg:<id>"`, `"end"`, or seconds. Words inside a card (`moves`, `strike_at`, `row_at`...) are searched after the
  card's own `at`. `x: "center"` centres the card.
- `from`: fly-in direction `left` | `right` | `above` | `below` | `front` (default: from the card's side of the head).
- `moves`: re-arrangements on words, offsets from the card's home: `dx`, `dy`, `rot`, `scale`, `ry` (3D turn), `o`
  (opacity, to dim a card that fans back), `blur`. Use them to stack, fan, dock or make room.
- `strike_at`: a red strike draws through the card on that word, then it lifts, tips and falls out away from the face
  (the card's `until` is ignored).
- `exit`: `fly` (default: back into depth, 0.22 s, ends on the `until` frame) or `cut` (hard off on the cut frame).
- `sfx`: `auto` (a soft swish for cards, a pop for chips), a sound name, or `off`; `sfx_gain` in dB.
- `group`: cluster id. Cards whose lifetimes overlap form one cluster automatically; the cluster is the beat's hero
  (QA hero_scale measures its span), so build each topic as a cluster around the head.
- `hud`: a step counter. Dots pop in on `at`, glide up to `dock_y` on `dock_at`, each `steps` entry grows its dot into a
  labelled pill on its word.
- `behind`: one accent word per moment. Live by default: the word is HTML (letters rise out of a mask, sink back out),
  a graded, edge-cleaned cut-out clip of the speaker plays above it only in its window, and both follow the camera.
  `"live": false` bakes it into the base plate the old way.
- Place cards in the wall space above/beside the head: QA fails any frame where a card touches the face box.

## Look rules

Entrances fly in from a visible state on the word frame: 3D (perspective, rotateY/X, z), motion blur that clears in
0.2 s, land on back.out(1.4) in 0.5 s while the contact shadow tightens. Then a slow seeded orbit (two sine yoyos).
Exits are 2x faster than entrances. One new card per phrase; a topic change re-arranges the cluster instead of
piling on. Captions: one word at a time, trailing punctuation dropped, never under the chin (placed from the face
track with camera headroom). Sound on entrances only: a soft swish per card, a pop per chip or HUD step, a thump
under the behind-head word, a chime when a status value stamps; all 20 LU under the voice. No music, no grain.
