# Editorial UI

The flagship look. On the hook and on every punchline your background is cut away and you sit on a solid colour
set. A huge serif headline sits BEHIND your head, small subtitles ride in a dark pill at chest height, and cream UI
cards land on their words: a status pill, an AI prompt pill that types and turns into a DONE chip, a checklist panel,
a magazine cover frame and a countdown. Between punchlines it cuts back to your real room. The set colour changes
on beat changes (brand colour, ink, bone, ember, slate, gold) and the headline colour flips with it to keep contrast.

Motion v2 adds the **takeover**: on a numbered point the room opens into a designed paper page through a circle that
starts behind your head, you stay in front as a live cut-out and step aside, huge serif words land behind your head
letter by letter (the previous word recedes behind it, blurred), a line chart can draw itself on the page, a side
tracker fills the step you are on, and a ghost numeral and a typed kicker frame it. On the colour set, a new headline
now pushes the old one back into a blurred ghost, and a colour switch opens as a circle from behind your head. Room
cards fly in in 3D (tilt, blur, from below) and status chips type their text.

Needs a cut-out of you: BiRefNet (portrait) runs on the set and takeover frames only, so it takes a few extra minutes.

## Run it

```bash
VENV=~/.reel-room/venv/bin/python
T=~/reel-room/skills/reel/templates
$VENV $T/split/facetrack.py P --step 3          # per-frame face track (once)
$VENV $T/editorial-ui/matte_infer.py P          # BiRefNet matte on the set frames (long: run in the background)
$VENV $T/editorial-ui/make.py P --out OUT        # bake + compose + lint + render + sound + loop + poster + QA
```

The matte pass takes about 8 to 15 s per set frame on an M-series CPU (CoreML cannot compile this model). Frames
are cached in `P/work/matte/raw/`, so it resumes where it stopped; run it again after changing which cuts are on the
set. Without them `bake.py` falls back to `assets/aroll_matte.webm` (u2net, from engine/cutout.py) and
`qa/set_report.json` fails `matte_source`.

Outputs in `OUT/`: `demo.mp4` (1080x1920, 30 fps, ~9.5 Mbps, -14 LUFS, true peak <= -1.5 dBTP, voice untouched,
UI SFX 20 LU under the voice), `demo-voiceonly.mp4`, `loop.mp4` (6 s, silent, < 4 MB), `poster.jpg`, and `qa/`
(`report.json`, `set_report.json`, `contact.jpg` one frame per beat, `switches.jpg` N-1 | N | N+1 per event,
`overview.jpg`, `face.jpg`, `matte_edges.jpg`).

Quick looks without a render: `$VENV bake.py P --stills 20,110,400` writes `P/work/stills/*.png`.

## Files

| file | job |
|---|---|
| `plan.py` | segments -> set, room or takeover, punch-in, set colour per frame, face geometry (face track mapped through the punch-in and the takeover cut-out move), headline and card frames, subtitle rows |
| `takeover.py` | the takeover scene: reveal, cut-out step-aside keys, kicker, ghost numeral, tracker, words behind the head, line chart, rack focus |
| `layers.py` | each headline line drawn once in headless Chrome (canvas, bundled serif) as a transparent PNG + ink box |
| `bake.py` | the set, frame by frame: plate (glow, vignette, grain) -> headline (masked rise) -> contact shadow -> refined speaker -> `assets/base.mp4` |
| `matte_infer.py` | BiRefNet-portrait matte per set frame, cached |
| `compose.py` | HyperFrames composition over `base.mp4`: cards, cover frame, countdown, subtitles, SFX cues, QA events |
| `etheme.py` | tokens from brand.json, palette schemes (contrast-checked type colour), bundled fonts |
| `make.py` | the whole run + set QA |
| `style.json` | defaults (every key can be overridden in project.json `"editorial"`) |
| `fonts/` | Playfair Display (roman + italic), DM Sans, JetBrains Mono, all SIL OFL 1.1 |

## Config (`project.json` -> `"editorial"`)

```json
"editorial": {
  "beats": {
    "hook":  {"scene": "set", "set": "brand",
              "headlines": [{"at": 0, "text": "GET IN|SHAPE"}, {"at": "@fast", "text": "_Fast._"},
                            {"at": "@5", "text": "5|THINGS", "set": "bone"}]},
    "cred1": {"scene": "set", "set": "ink",
              "headlines": [{"at": 0, "text": "NEW HERE"}, {"at": "@physician", "text": "_Physician._"}],
              "cards": [{"kind": "cover", "at": "@physician", "issue": "NO. 01", "date": "OCTOBER 2026", "tag": "THE DOCTOR ISSUE"}]},
    "cred2": {"scene": "room", "cards": [{"kind": "status", "at": "@health", "label": "HEALTH COACH", "text": "in residency"}]},
    "n1b":   {"scene": "room", "cards": [{"kind": "prompt", "at": "@full", "text": "order a full comprehensive panel",
                                          "send": "@panel+0.25", "done": "@that", "done_text": "panel ordered"}]},
    "n1c":   {"scene": "room", "cards": [{"kind": "panel", "title": "FULL PANEL",
                                          "rows": [{"text": "Metabolic health"}, {"text": "Fasting insulin levels", "at": "@fasting", "hl": true}]}]},
    "n2":    {"scene": "set", "set": "slate", "cards": [{"kind": "countdown", "at": "@come", "label": "DEADLINE SET"}]}
  },
  "loop": {"t0": 0.0}, "poster": {"t": 3.7}
}
```

Segments without an entry: the first cut and every edl `number` insert go on the set (headline from the hook / the
number title), everything else stays in the room.

### Beat keys

| key | meaning |
|---|---|
| `scene` | `"set"` (cut-out on the colour plate), `"room"` (original footage) or `"takeover"` (page + live cut-out, below). Switches happen on cut frames |
| `set` | palette key for the plate: `brand`, `ink`, `bone`, `ember`, `slate`, `gold` (or your own in `palette`) |
| `zoom` | set punch-in about the face (default `set.zoom` 1.12; 1.0 when the cut is already punched in the edl) |
| `headlines` | list, each shows from `at` until the next one or the cut. `text`: `|` = new line, `_word_` = italic accent colour. Optional `set` switches the plate colour on that word (hard switch, word-synced), `bottom` (px), `same: true` (one size for all lines), `cx` |
| `cards` | list of cards (below). Room cards stack from y 244 down and must end above the head (compose warns) |

Time anchors everywhere: seconds after the cut, `"@word"`, `"@word:2"` (2nd time it is said), `"@word+0.2"`.

### Takeover beats (`"scene": "takeover"`, `takeover.py`)

```json
"tracker": {"title": "5 THINGS TO GET IN SHAPE", "items": ["Blood work", "Deadline"], "count": 5},
"beats": {
  "n1a": {"scene": "takeover", "step": 1, "step_at": "@start",
          "words": [{"at": 0, "text": "_No. 1_"}, {"at": "@blood", "text": "BLOOD|WORK"}]},
  "n1d": {"scene": "takeover", "step": 1, "kicker": "THE ONE NUMBER TO ASK FOR",
          "chart": {"title": "FASTING INSULIN", "unit": "uIU/mL", "values": [3.6, 4.3, 5.2, 6.3, 7.7, 9.0, 10.2],
                    "limit": 7, "at": 0, "cross": "@over", "note": "insulin resistance", "note_at": "@that"}},
  "n2":  {"scene": "takeover", "step": 2, "step_at": "@2",
          "words": [{"at": 0, "text": "_No. 2_"}, {"at": "@deadline", "text": "DEADLINE"}],
          "cards": [{"kind": "countdown", "at": "@come", "label": "DEADLINE SET"}]}
}
```

| key | meaning |
|---|---|
| `words` | huge serif words behind the head, same markup as headlines (`|` new line, `_x_` italic accent). Each lands letter by letter out of a mask with blur; the previous one recedes (smaller, higher, blurred) and stays as a ghost |
| `step` / `step_at` | the side tracker fills this step on that word (step > 1: the previous step un-fills and keeps a dark label, the ghost numeral rolls) |
| `kicker` | mono caps line typed top left (default `tracker.title`); top right reads `PART 0N / 0M` |
| `chart` | line chart on the page: `values`, optional `limit` (dashed line; the part above it turns red), `at` (draw start), `cross` (the word where the line crosses the limit: jolt, glow, the limit label stamps), `note` + `note_at` (serif note with a drawn arrow), `title`, `unit`, `limit_label` |
| `page` | palette key of the paper (default `bone`) |
| `reveal` | `{"from": "head" \| "chest" \| [x, y], "delay": 0.22, "dur": 0.6}`: where the circle opens |
| `subject` | `{"scale": 0.9, "x": -150}`: where the cut-out settles (the right column is the tracker's) |
| `cards` | as on any beat; they stack from `takeover.content_top` (330) under the kicker |

Without config, every edl `number` insert becomes a takeover (`takeover.auto`, default true): "No. N" then the title
on its first spoken word, tracker items from the number titles, count from the highest number or the hook. The cut
into a takeover is a whip (engine Motion v2), then the circle opens. Bake writes `assets/tko_<seg>.webm` (VP9 +
alpha, bt709, + 3 transparent frames for the renderer's coverage gate); the page and the cut-out ride the engine
camera (`<!--mvcam-->` block, stylekit/kit.py).

### Cards

| kind | keys |
|---|---|
| `status` | `label` (mono caps), `text`, `tone`: `gold` / `flag` / `ink` |
| `prompt` | `text` (typed at >= `prompt.cps`, finishes before `send`), `label` (optional small caps label above the text; default `prompt.label`, empty = no label), `send` (arrow press, SENT + dots), `done` + `done_text` (turns into a DONE chip) |
| `panel` | `title`, `meta` (right corner, default "N ITEMS"), `rows: [{text, at, hl, show}]`: rows are visible from the start (`show: "at"` makes one appear on its word), each ticks on its `at`, `hl` adds the gold highlight |
| `cover` | magazine frame: gold double border, `issue`, `tag`, `date` kicker row, barcode (`code`); lands with a shutter and a flash. The current headline is the masthead |
| `countdown` | `label`, `days` (default `countdown.days` 84 = 12 weeks; counts down from DAYS:00:00:00 after a short digit roll), `first_tick_s` |

### Style keys (`style.json`, override under `"editorial"`)

| key | default | meaning |
|---|---|---|
| `palette.<key>` | brand, ink, bone, ember, slate, gold | `{plate, type, accent}`; type flips to ink or cream when contrast < 3:1 (large text) |
| `set.default` | `brand` | plate when a beat names none |
| `set.zoom` / `grain` / `vignette` / `glow` | 1.12 / 3.2 / 0.42 / 0.55 | the set look |
| `set.shadow` | opacity .42, blur 34, dy 26 | contact shadow on plate and type (x0.75 on light plates) |
| `set.edge` | erode 1, feather 0.8, wrap 0.22, temporal on | matte refinement |
| `headline` | max_w 1000, max_px 330, min_px 120, overlap 0.95, rise_s 0.42 | `overlap`: how far the letters tuck behind the head (share of cap-to-brow height) |
| `subtitle` | font `ui`, px 42, max_words 4, max_chars 24, min_top 1290, max_top 1402, dim .58 | `font: "serif"` for serif subtitles |
| `band.top` | 244 | first card row (Reels safe zone top is 220) |
| `sfx.enabled` | true | UI sounds on entrances (thump, pop, key, click, chime, shutter, tick), all synthesized, 20 LU under the voice |
| `prompt.label` / `prompt.cps` | "" (no label) / 26 | |
| `countdown.days` | 84 | countdown start (12 weeks) |
| `headline.ghost` | true | the previous headline recedes into a blurred ghost behind the new one (set) |
| `takeover.*` | see style.json | `page`, `reveal`, `subject`, `words` (max_px 270, italic_px 200, overlap 0.55), `tracker` (x 742, top 880, w 236), `content_top`, `ghost`, `rack` |

Brand (`brand.json`): `colors.set` (or `accent`), `colors.cream`, `colors.gold`, `colors.ink`, `fonts.serif/ui/mono`.

## Quality rules it enforces

- Nothing over the face: cards and subtitles are placed from the per-frame face track mapped through the punch-in;
  QA checks every 3rd frame. Headlines sit behind the head and `bake_qa.json` counts headline pixels visible inside
  the face box (must be ~0).
- Reels safe zone: nothing readable above y 220 or below 1470, right 100 px clear below y 1155.
- Subtitles are the words.json text exactly (phrase chunks, no orphans), each lands on its first word's frame.
- Set/room switches, colour switches and every card land on their frame (QA `switches.jpg`).
- Matte: BiRefNet on every set frame, blob cleanup (only the body and what touches it), motion-gated temporal
  smoothing, 1 px erode + feather, blur-fusion foreground colour estimation (no wall-colour halo), light wrap.
- No em dashes anywhere.

## Plan compiler (compile_plan.py --style editorial-ui, 2026-10-13)

The adapter (`engine/compile/editorial_ui.py`) writes `"editorial"` for you: the hook and the best word beats (4 at
most) go on the colour set with the phrase behind the head; the rest stay in the room with an everyday card in the
upper third (above the face, else beside the head, never on the torso; `kitcards.py`). Extra keys it uses:

| key | meaning |
|---|---|
| card `{"kind": "beat", "comp": "ed-headline", "args": {...}}` | everyday editorial card (templates/kit/beats_editorial.py) |
| card `{"kind": "kit", "comp": "<rrkit id>", "args": {...}}` | any kit piece in the band |
| card `{"kind": "hero", "comp": "word-stamp", "matte": true, "end_seg": "s01a"}` | library hero in the camera block; `matte` lays the cut-out span over it (behind the head) |
| `matte.source: "cache"` | set-frame masks from engine/cutout_cache.py (counted as `cutout` in set_report, not a fallback) |
| `bake: {"workers": 3, "cache": true}` | per-cut bake cache (bake_cache.py); `bake_par.py` bakes spans in parallel without the cache |
| `set.edge.fg_half` | foreground colour estimation with half-resolution blur statistics (bake_fast.py) |
