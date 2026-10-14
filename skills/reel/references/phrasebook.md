# Say this to get that (phrasebook)

Most people do not know how to prompt an editor. The Room's **Say this** tab (and the quick asks on the Dailies "This
beat" card) lists plain phrases. Tapping "Use this" writes a frame-pinned note with the phrase as its text, so nobody
types a prompt. Data: `styles/phrasebook.json` (groups, phrases, examples). Publish it next to the page as `phrasebook.json`
(`files` on the Room publish, SKILL.md section 2); the page reads it on load. The page also carries the same list built
in, used when the file is missing (local preview, a Room published before this). When you change the JSON, update the
`PHRASEBOOK` constant in `room/reel-room.html` too (groups, examples, and per item id, group, say, does, action,
needs_word), then republish the Room with the file. `tests/test_phrasebook.py` fails when the two drift.

## How a phrase reaches you

- A note `notes/{id}` with `text` = the phrase (`{word}` already filled with the word spoken at the pinned frame),
  `phrase` = the phrase id (`"free"` for the free-text box), `seg` = the segment under the playhead, plus the usual
  `t`, `round`, `status:"open"`. Treat it like any note: one concrete edit, then `status:"fixed"` and a plain `reply`.
- Two phrases are structured instead of notes when a cut exists: "Make this part simpler" writes
  `beat_changes {kind:"simpler"}`, "Show off on this part" writes `beat_changes {kind:"level", level:"showreel"}`.
  Apply them with `rounds.py` (below).
- Before the first cut, "Use this" appends the phrase to the storyboard change box instead. It reaches you as
  `storyboard/approval.note`.
- The note's `seg` is the segment to change. "Here" and "this part" mean that segment only. Change nothing else.

## Phrase id -> what you do

Segment overrides go on the edl.json segment as `"motion": {...}` (`references/motion.md` section 1). Level changes go
through `rounds.py` so they are logged and survive `snips.py undo`. After any of these, rebuild per the `rebuild` value
`rounds.py` prints (`render` = skip assemble; `assemble` = timing moved).

| id | phrase | action |
|---|---|---|
| `simpler-here` | Make this part simpler | `rounds.py P simpler <seg>` (one level down; at Simple, say so and offer "Remove the graphics here") |
| `no-graphics-here` | Remove the graphics here | drop `top` on the segment (and project.json `beats`/`overlays` rows inside its window); set `mode:"full"` if it was split |
| `just-captions` | Just captions on this part | `mode:"full"`, no `top`, `rounds.py P level <seg> simple`, plain captions for the segment if the style supports it |
| `fewer-zooms` | Fewer zooms | segment `motion.camera:"still"` (no punches, push or reframes in that shot) |
| `no-sfx` | No sound effects | project.json `motion.sfx:"off"` (whole reel; voice-only is always delivered anyway) |
| `no-transition` | Plain cut here, no transition | segment `motion.transition:"none"` (the cut INTO this segment) |
| `whip-here` | Add a whip here | segment `motion.transition:"whip"` |
| `hook-harder` | Make the hook hit harder | `rounds.py P level <first seg> showreel`, plus segment `motion.punch:"@<payoff word>"`; re-check the hook card with `hook-school.md` |
| `punch-line` | Punch in on "{word}" | segment `motion.camera:"punch"`, `motion.punch:"@{word}"` |
| `show-off-here` | Show off on this part | `rounds.py P level <seg> showreel`; build the beat with the showreel clause (`motion.md` section 8) |
| `more-sfx` | More sound effects | project.json `motion.sfx:"full"` |
| `word-behind` | Big word behind my head on "{word}" | `motion.behind` row `{text: WORD in caps, at:"@word", until:"@next phrase word"}`; needs `cutout.py` (`motion.md` section 5) |
| `behind-head-auto` | Put the key word behind me | same, you pick the payoff word of the line |
| `type-prompt` | Type it like a prompt | kit component `typer` |
| `tick-off` | Tick them off as I say them | kit `checklist-tick` (split engine: `checklist` insert with item anchors) |
| `count-up` | Count it up | kit `odometer` (split engine: `number` insert) |
| `arrow-at` | Draw an arrow at it | kit `annotation-arrow` `kind:"arrow"` |
| `circle-it` | Circle it | kit `annotation-arrow` `kind:"circle"` |
| `strike-it` | Strike "{word}" out | kit `label-pill` (split engine: `strike_pill` insert) |
| `add-up-price` | Show the cost adding up | kit `receipt` |
| `before-after` | Show a before and after | kit `before-after` (split engine: `flip` insert) |
| `spotlight` | Spotlight this part | kit `spotlight` |
| `show-steps` | Show the steps as I go | kit `stepper` |
| `progress` | Fill a progress bar | kit `progress-bar` |
| `comment-dm` | End on the comment-for-DM | kit `comment-cta` (keyword from brand.json `cta`; no auto-DM set up: ask first) |
| `into-phone` | Shrink me into a phone | kit `phone-frame` |
| `show-chart` | Show a chart here | split engine `table` insert; motion-editorial `cycle_chart` or `gauge`. Numbers only from what was said |
| `show-study` | Show the chart from the study | kit `evidence-chart` (line or bar chart rebuilt from the cited figure, `stat` stamps on its word, `highlight` rings one bar). Needs the citation and the figure's values: ask for them or read them off the creator's own card, never invent numbers |
| `title-stamp-it` | Stamp it as a big headline | hero `title-stamp` (text = the segment's key phrase, verbatim; `sub` = the next words; colour set from the section) |
| `roll-number` | Roll the number up and step it | hero `money-counter` (`steps` = every number said, each on its word; `unit`/`label` from the line) |
| `draw-the-drop` | Draw the drop on a chart | hero `cycle-chart` (`shape` drop / dip / rise, labels from the line, `stamp` on the payoff word) |
| `study-number-big` | Slam the study number in big | hero `evidence-hero` (needs the citation and the figure's values in `script.md` or `work/sources.txt`; never invent numbers) |
| `editing-timeline` | Show the editing timeline of this video | hero `nle-timeline` (the compiler fills the real cuts, captions and graphics of this reel) |
| `fire-timeline` | Set the timeline on fire | hero `fire-timeline` (`ignite` on the build-up word, `burn` on the payoff word) |
| `stamp-word` | Stamp "{word}" huge | hero `word-stamp` (`word` = {word}; behind the head with `cutout.py`, else on a slab above it) |
| `palette-fan` | Fan out the styles like a paint deck | hero `palette-fan` (thumbnails: the creator's own previews or stills; `pick_at` on the payoff word) |
| `video-chapters` | Show it as a video with chapters | hero `video-card` (`title` + 2 to 4 `chapters` from the line, `play_at` on the word) |
| `grid-of-me` | Shrink me into a grid | hero `grid-collapse` (tiles = stills of the creator's own footage; full-frame beat, one shot) |
| `magazine-cover` | Make it a magazine cover | hero `magazine-cover` (masthead + coverlines from the line; full-frame beat) |
| `orbit-my-reels` | Orbit my reels around me | hero `reel-orbit` (the creator's own reel thumbnails: `assets/reels/*.jpg`, else stills of the A-roll) |
| `moodier` | Grade it moodier here | `grade.py` grades the whole reel. Say so in one line and offer the `dark` grade for the whole reel |
| `tighter` | Tighter | trim pauses inside the segment with `splice.py` (cuts only in measured silence), never speed up |
| `breathe` | Let this breathe | extend the segment's `out` into the following silence (up to 0.5 s), re-run `splice.py snap/joins` |
| `cut-pause` | Cut the pause before "{word}" | a snip of the silence before that word (`snips.py`, cut time), then the usual rebuild |
| `hold-face` | Stay on my face longer here | delay the segment's insert entrance (`at_word` later, or `beats` row `at` + 0.5 to 1 s) |

Kit components: ids, args and the `say` list live in `templates/kit/rrkit.py` (`rrkit.COMPONENTS[id]`) and the kit
README once it lands. Heroes (`hero ...` rows) are library heroes (`references/kit.md` section 5): write the segment's
`top` as `{"insert": "hero", "args": {"comp": "<id>", ...contract}}` and validate the args with
`engine/hero_schema.py` (`validate(id, args, line)`). A beat gets one hero: if the segment already has one, replace
it, do not stack.

Free text (`phrase:"free"`): map it to the closest row above. If two readings are possible, ask one short question in
chat. "Same as round 2 here" means `rounds.py P use <seg> 2`.

## Preview loops (`phrasebook/catalog`)

Cards show "Preview soon" until you fill `phrasebook/catalog`:

```json
{"items": [{"id": "type-prompt", "preview": "<asset url>", "preview_kind": "video", "poster": "<asset url>?"}]}
```

Loops: kit phrases use `<loops_dir>/<component>.mp4` (`loops_dir` in `phrasebook.json`, the kit ids in `kit_ids`);
hero phrases use `<hero_loops_dir>/<component>.mp4` (`hero_ids`).
Upload each with the Artifact tool (`asset: true`, short muted mp4 under 2 MB), then write the catalog once. Phrases
with `loop` set (whip, punch, behind my head, showreel hook, chart) need a short engine clip instead; until one
exists leave them out of the catalog. Never upload the same loop twice per Room: one asset per component, reuse the
url for every phrase that maps to it.
