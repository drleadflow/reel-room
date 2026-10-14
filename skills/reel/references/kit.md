# Component kit: 14 pro motion pieces + the hero library, every style can drop in

Code: `templates/kit/` (`rrkit.py` API, `rrkit_base.py` core, `comps_ui.py` + `comps_fx.py` + `comps_pip.py` markup,
`kit_core.js` + `kit_ui.js` + `kit_fx.js` + `kit_pip.js` runtime `window.RRK`, `kit.css`, `gallery.py`, `test_rrkit.py`).
Gallery: `<gallery-out>/` (one mp4 per piece, `loops/<id>.mp4`, `contact_sheet.jpg`).

Every piece is built on the Motion v2 runtime (`references/motion.md`): intent eases (`RRM.EASE`), every event on its
frame (`RRM.q`), entrances `fromTo(immediateRender:false)`, per-frame values as one `tl.set` per frame, seeded
randomness only. Colours and fonts come from brand.json only. Hero entrances use blur + scale + offset; exits are about
twice as fast. Everything sits inside the Reels safe zone by default (named spots, see `pos`). No grain, no em dashes.

## 1. Use it

```python
import sys; sys.path.insert(0, SK + "/templates/kit"); import rrkit

# split engine (inside an insert fn(cx, beat, args)): numbers are seconds after the beat start
k = rrkit.Kit.for_split(cx, beat)
html = rrkit.mount(cx, k.typer("cut the pauses", at="@cut", type_until="@pauses^", send="@then"))

# full-frame styles (stylekit Project + TL): numbers are cut seconds
k = rrkit.Kit.for_stylekit(proj)
html = rrkit.mount(tl, k.odometer(7.0, decimals=1, at="@insulin", land="@7", label="FASTING INSULIN"))

# hand-built page: a dict collects the tweens and the mixer events
host = {}; html = rrkit.mount(host, piece)        # host["js"] lines go inside the timeline builder, host["events"]
                                                   # into engine/motion/mixer.build_bus
# planner / JSON: by component id
piece = rrkit.build(k, "checklist-tick", items=[...], ticks=[...])
```

`mount()` returns the piece's HTML (put it in the beat / body), pushes its one `RRK.<name>(tl, '#id', cfg)` call into the
timeline and its SFX into the host (split: `cx.event`, stylekit: `tl.cue`). The first mount on a page also inlines the
kit runtime and stylesheet; nothing else to load. The page must load GSAP (and `rrm-motion.js` when motion is on; the
kit carries the same ease table as a fallback).

**Time specs** (every `at`, `until`, `send`, `ticks[i]`, ...):

| spec | means |
|---|---|
| `1.2` | seconds after the kit's base (split: beat start; full-frame: cut seconds) |
| `"@word"` | start of the first matching word, searched IN ORDER after the piece's previous anchor, minus a lead (visual 0.04 s, stamp 0.03, type 0.05) |
| `"@word:2"` | the second match |
| `"@word^"` | the word's END (no lead): typing that runs to the end of a word |
| `"@word+0.2"` | offset |
| missing word | falls back to the previous anchor + a sensible default, with a WARN |

**Common args**: `pos` (`top` above the head, `upper`, `center`, `lower` above captions, `left`, `right`) or explicit
`x`, `y`; `w`; `theme` (`light` / `dark` card); `until` (end; default: the split beat end or a short hold);
`exit` (`blur`, `lift`, `fold`, `fall`, `cut`, per piece extras below); `z`.

**SFX**: each piece emits `{t, kind, sound, what, level}`; `light` events are the hero moments (opens, sends, ticks,
stamps), `full` adds typing ticks and rows. `mount(host, piece, sfx_level="light")` (default), `"full"`, or `"off"`.
Sounds come from `engine/motion/sfxkit.py` (stylekit hosts map to `stylekit/sfx.py` names) and the mixer keeps them
at least 18 dB under the voice. Never played aloud by the kit; QA listens through the stems.

## 2. The pieces

### typer: "type it like a prompt"
A pill with a spark icon opens into a prompt bar, types the text across the spoken words, sends (button press, the
arrow leaves, a ring spins, label PROMPT -> SENT), the result rolls in (DONE, check, accent button), closes back to
the pill. Typing and the pill/bar clip adapted from reel-kit `fx/prompt-bar` (MIT).
```python
k.typer(text, at=0, type_at=None, type_until=None, send=None, done=None, done_at=None, until=None,
        labels=("PROMPT", "SENT", "DONE"), pos="top", w=960, theme="light", exit="pill")
```
Demo: `k.typer("order a full metabolic panel", type_at="@get", type_until="@panel^", send="@that", done="Full panel ordered", done_at="@everything")`

### checklist-tick: "tick them off"
A card (optional title) whose rows rise in; each item ticks on its word: the circle pops, the check draws, the row
highlight sweeps in, the label goes to full ink. `style="strike"` crosses items out instead (to-do look).
```python
k.checklist(items, ticks=None, at=0, until=None, title=None, style="check", pos="top", w=860)
```
`ticks`: one anchor per item; `None` = default spacing, `False` = never ticks.
Demo: `k.checklist(["Metabolic panel", "On the order", "Fasting insulin", "Insulin levels"], ticks=["@metabolic", "@sure", "@fasting", "@levels"], title="Your blood work")`

### progress-bar: "fill the bar"
A card with a label, a rolling percentage and a track: the fill and its glowing lead dot glide to each value on its
word, milestone marks pop, optional notes swap under the bar; at 100 the bar turns the highlight colour and the card
takes a beat.
```python
k.progress(steps, at=0, until=None, label="PROGRESS", start=0, notes=None, unit="%", show_pct=True, pos="top", w=900)
```
Demo: `k.progress([("@shape", 25), ("@fast", 55), ("@humanly", 80), ("@possible", 100)], label="GET IN SHAPE")`

### odometer: "count it up"
A mechanical counter: digit drums roll (with motion blur) from `start` and lock left to right, the last drum on the
`land` word; the number stamps, a small seeded shake, the suffix slides in, then a slow drift while it holds.
```python
k.odometer(value, at=0, land=None, until=None, start=0, decimals=0, prefix="", suffix="", label=None,
           size=230, color="accent", card=False, pos="top")
```
Demo: `k.odometer(7.0, decimals=1, at="@insulin", land="@7", label="FASTING INSULIN", prefix=">", suffix="µIU/mL", size=250)`

### label-pill: "pop a label", "strike it out"
A label or logo pill pops in (overshoot + blur) with a burst of rays; on `strike` a line crosses it, it desaturates,
hops and tumbles out of frame. Without a strike it leaves with `exit` at `until`.
```python
k.pill(text, at=0, strike=None, until=None, exit="tumble", tone="accent", icon=None, logo=None, burst=True, size=56, pos="top")
```
`tone`: `accent`, `light`, `ink`, `hl`. `logo`: an image path (a brand logo); `icon`: inline SVG.
Demo: `k.pill("Ozempic", at="@ozempic", strike="@thing", size=88)`

### receipt: "print the receipt", "price stack"
A slot slides in and a paper receipt prints top-down out of it: each row prints on its word (the torn edge feeds
down), struck `was` prices cross out, the total rolls up, an optional stamp slams on with a shake.
```python
k.receipt(rows, at=0, prints=None, total=None, total_at=None, stamp=None, stamp_at=None, until=None,
          title="RECEIPT", sub=None, currency="$", pos="top", w=720)
```
`rows`: `(label, price)` or `(label, price, was)`. `total` defaults to the sum.
Demo: `k.receipt([("Fasting insulin", 39), ("HbA1c", 29), ("Lipid panel", 35, 49)], prints=["@fasting", "@level", "@tell"], total_at="@about", stamp="PAID", stamp_at="@resistance", title="LAB PANEL")`

### comment-cta: "comment for the DM"
A comment field types the keyword on its word and posts (button press, heart pops and fills), then the DM card lands:
typing dots, the creator's message bubble, a link card with the keyword chip, "Seen". Generic UI in brand colours, no
platform logos. Field flow adapted from reel-kit `fx/comment-cta` (MIT). One link per DM (house rule).
```python
k.comment_dm(keyword, at=0, type_at=None, post=None, dm_at=None, until=None, handle=None, viewer="you",
             comment=None, dm_text=None, link_text=None, link_sub=None, avatar=None, pos="top", w=900)
```
Demo: `k.comment_dm("SHAPE", type_at=0.5, post=1.25, dm_at=1.75, dm_text="Here's your SHAPE plan", link_text="5-step shape plan")`

### stepper: "show the steps", "part 1 of 4"
`layout="list"`: a card (optional title) with numbered rows sliding in; activating a step fills its pill, flips the
number and label to light with a small punch; the previous step turns into a drawn check. `layout="bar"`: a
segmented HUD with "PART 01 / 05" (the number rolls) and the current step's name.
```python
k.stepper(steps, at=0, active=None, until=None, layout="list", kicker="PART", title=None, card=True, pos="left", w=None)
```
`active`: one anchor per step (None = that step never activates).
Demo: `k.stepper(["Blood work", "Deadline", "Food", "Training", "Sleep"], active=[0.35, "@2"], title="5 things")`

### annotation-arrow: "draw an arrow at it", "circle it", "underline it"
A hand-drawn mark (seeded wobble, so it looks drawn, the same every render) draws on: an arrow (shaft then the two
head strokes), a loop around a box, or an underline (optionally double); the handwritten label (brand hand font)
writes in letter by letter. Exit erases the stroke.
```python
k.annotate(target, kind="arrow", at=0, label=None, frm=None, label_at=None, until=None, color="accent",
           width=9, bend=0.22, size=84, seed=7, pad=26, double=False, exit="erase")
```
`target`: arrow = the point `(x, y)` it points at (point next to a face, never on it); circle/underline = box
`(x, y, w, h)`. `frm` = where the arrow starts (the label sits there).
Demo: `k.annotate((face_x - 70, face_y + 80), frm=(160, 470), label="physician", at="@physician")`

### phone-frame: "shrink me into a phone"
The speaker shrinks into a phone (bezel, status bar, reel side rail, handle and caption) over the brand ground with a
slight 3D tilt drift, optional title above, then grows back to full frame on `back`. Works by a frame-synced copy of
the plate (`src`) inside the piece, so the host's camera and layout are never touched; the copy matches the plate on
its first frame, so the start and the hand-back are invisible.
```python
k.phone(at=0, back=None, until=None, src="assets/aroll.mp4", media_offset=0.0, cx=540, cy=900, scale=0.5,
        radius=70, ring=18, tilt=5, chrome="reel", handle=None, caption=None, title=None, track=None)
```
`src` must play in composition time (the split/stylekit plate does; else set `media_offset`). Do not let a cut or a
transition land inside the window (the copy shows the plate's picture, not the host's camera move).
Demo: `k.phone(at=0.25, until=4.5, title="Save this one", caption="5 things I'd do to get in shape", scale=0.56, cy=960)`

### before-after: "wipe before to after"
A tilted divider with a white line and a round handle lands on `rest` (overshoot), labels BEFORE / AFTER pop, then it
sweeps to `end` on `sweep`. `mode="full"` with no `before` is a look wipe: a live copy of the plate with
`before_filter` (flat, desaturated) wipes away to reveal the real picture. `mode="card"` puts two images in a rounded
card at `card=(x, y, w, h)`.
```python
k.before_after(at=0, sweep=None, until=None, before=None, after=None, mode="full", rest=0.6, end=0.0,
               labels=("BEFORE", "AFTER"), angle=7, src="assets/aroll.mp4", before_filter=..., card=None)
```
Demo: `k.before_after(at=0.15, sweep=2.3)`

### spotlight: "spotlight it", "dim everything else"
The frame dims except a soft-edged region (a dim layer with a hole), a thin brand ring marks it, the light glides to
the next region on each move, labels pop under each stop.
```python
k.spotlight(target, at=0, moves=None, until=None, shape="round", dim=0.62, feather=18, ring=True, label=None, pad=20)
```
`target`: `(x, y, w, h)` or `(cx, cy, r)`; `moves`: `[(anchor, target), ...]`; `label`: text or a list per stop.
Demo: `k.spotlight((cx, cy, r), at=0.15, moves=[("@over", (mic_x, mic_y, 130))], label=[None, "the mic"])`

### head-bubble: "put my head in a bubble", "picture in picture me"
The speaker shrinks from the plate into a circle in a top corner while a full-screen graphic plays behind, then grows
back into the plate on `back`. In: the mask circle tightens around the face on a damped spring (about 4 % overshoot),
the circle travels to its corner on the camera ease, a soft ring and drop shadow fade in as it lands; the circle
follows the tracked face, so the face stays centred. Out: it travels home and opens back into the plate; the last
frame is the plate exactly. Same frame-synced plate copy as phone-frame, keyed one frame at a time from Python.
```python
k.head_bubble(at=0, back=None, src="assets/aroll.mp4", corner="tl", size=300, ring=True, label=None, until=None,
              face=(540, 900, 190), fit=1.18, plate=None, clip=None, behind=None, ground=True, vignette=0.0)
```
`corner`: `tl` or `tr` (60 px in, top at y 250). `face`: `(x, y, h)` or `[(t, x, y, h), ...]` screen px (h = face
height; the circle radius is `fit` x h). `plate`: the host plate's transform `{x, y, scale, ox, oy}` (default a full
frame plate); `clip`: the plate's visible region `(x0, y0, x1, y1)`, e.g. `(0, 960, 1080, 1920)` under a split seam;
`vignette`: the host vignette strength, so the copy matches it. `behind`: host html (a diagram), an image or a video,
drawn full frame on the brand `ground`. Meta `cam_sel` is the copy's camera wrapper: a host with a camera rig keys it
with the same rows as its own camera (the split engine does, `cx.cam_followers`).
**One shot only**: no cut and no whole-frame transition inside `[at, back + 0.56 s]` (the split engine warns, and
turns the transition off on the cut the bubble starts from). Kallaway preset: a segment `"bubble": {...}`.
Demo: `k.head_bubble(at=0.3, back="@metabolic", face=face_rows, behind=diagram_html, label="Your Name")`

### evidence-chart: "show the study", "chart the numbers"
A cited line or bar chart rebuilt from the study's own figure (values traced from the figure, never invented). The card
lands, lines draw (markers pop along them) or bars grow group by group until `draw`, the takeaway number stamps on
`stamp` with its label sliding in, and for bars `highlight` rings one bar on `highlight_at` while the rest dim. The
citation row (`SOURCE` + `citation`) is always on the card; a missing citation is an error. The last series is the
"effect" series in the accent colour, the others step down from ink. `draw`, `stamp` and `highlight_at` each search
from the entrance, so the stamp word may come before the draw word. Code: `comps_chart.py` (own CSS and tweens, no
runtime JS), registered at the end of `rrkit.py`. Built from the showcase showcase vaping charts.
```python
k.evidence_chart(kind="line"|"bar", citation, series=[{name, values, marker?, color?}], labels, at=0.0, until=None,
                 draw=None, stat=None, stat_label=None, stamp=None, kicker=None, title=None, highlight=None,
                 highlight_at=None, y_max=None, y_label=None, x_label=None, pos="center", w=980, h=None, theme="light")
```
Demo: `k.evidence_chart(kind="line", citation="Chaumont et al., Sci Rep 2018", labels=["BSL","1","2","3"],
series=[{"name":"sham vape","values":[0,140,315,345]},{"name":"nicotine vape","values":[0,90,243,287]}],
stat="33%", stat_label="less blood-vessel dilation", stamp="@clamps", draw="@flow", y_label="PERFUSION UNIT")`
Rules: one chart per beat, held at least 2 s after `draw`; flag the claim in the round summary like any medical
number (SKILL.md hard rules). Test: `tests/test_evidence_chart.py`.

### Everyday editorial beats (beats_editorial.py, never in the hero catalogue)

`ed-headline` (serif headline + italic sub-line), `ed-number` (number slam + small context line), `ed-checklist`
(small card, header rule, rows tick on their words in spoken order), `ed-contrast` ('A' struck on its word, 'B' lands
in italic), `ed-kicker` (mono kicker over a serif headline). Layout `split` = the colour-set ground and the meta row
are there from the beat's first frame; `full` / `overlay` = a compact card in `area` ([y0, y1] or [y0, y1, x, w] beside
the head), sized to fit, clamped to the beat. Entrances are eased slides with a small overshoot. The plan compiler
fills them through `engine/compile/everyday.py` and validates every fill with `engine/beat_schema.py` (spoken words
and numbers only, anchors in the line); consecutive beats rotate treatments.

## 3. Rules for builders

- One hero per beat: a kit piece is the hero of its beat; do not stack two big pieces at once.
- Land on the word: give anchors, not seconds, whenever the line says the thing.
- Keep pieces off the face: `top` and `left` spots are clear of a centred speaker; check `annotate` targets and
  `spotlight` regions against the face track.
- `phone-frame`, `before-after` (full mode) and `head-bubble` carry their own video copy: use them inside one shot.
- QA tags: readable text uses `data-box="text"` (measured tight); anything with clipped overflow (odometer drums,
  rolling numbers) uses `data-box="glyph"` (element rect) so safe-zone and face checks see the visible box.
- Light SFX by default; never ask the kit for `full` on a teaching reel.
- New piece? Add the markup to `comps_*.py`, the animator to `kit_*.js`, the style to `kit.css`, a row in
  `rrkit.COMPONENTS` (id, method, plain-language `say` list), a demo in `gallery.py`, a section here.

## 4. Gallery and tests

```
python3 templates/kit/gallery.py --src <project with assets/aroll.mp4, words.json, brand.json, assets/fonts, work/facetrack.json> \
        --out <gallery-out> [--only typer,odometer] [--jobs 2] [--workers 3] [--snap 0.5,1.2]
python3 templates/kit/test_rrkit.py
```
Gallery output: `<id>.mp4` (voice + light SFX, -14 LUFS), `loops/<id>.mp4` (silent preview loop for the Room's
phrasebook), `contact_sheet.jpg` (5 frames per piece), `proj/<id>/` (the composition, `kit_meta.json` with the
resolved times and events).

## 5. Hero library (batch 1): premium, parameterised hero moments

Code: `templates/kit/heroes.py` (registry) + `heroes_base.py` (colour sets, stage, JS emitter with per-frame motion
blur, word clocks, the `@hero` contract) + `heroes_type.py`, `heroes_data.py`, `heroes_edit.py`, `heroes_card.py`,
`heroes_frame.py`, `heroes_fire.py`. Registered additively at the end of `rrkit.py` (`rrkit.COMPONENTS[id]["hero"] = True`,
`rrkit.HEROES` = the catalogue). Contract validator: `engine/hero_schema.py`. Gallery: `hero_gallery.py` (demos in
`hero_demos.py`) -> `<gallery-out>/heroes/<id>.mp4`, `loops/<id>.mp4`,
`contact_sheet.jpg`; code gates `hero_gates.py`; taste gate `hero_judge.py` (engine/judge.py, pairwise against the
hero-length the showcase reference matched in `heroes/refs/map.json`; split heroes against split-deck moments, charts and
full-frame heroes against editorial-ui moments); tests `test_heroes.py`.

A hero is one showreel moment a model can pick and fill in seconds: typed fields (text with max lengths, numbers,
'@word' anchors, brand colour sets), the layouts it can draw in, the shortest window it needs. Every hero: eased
entrances (snap / land / stamp, never linear), per-frame motion blur on fast moves, lands on its word, light SFX
cue points, no em dashes, no grain, faces never covered, inside the safe zone, at least 60 % of the frame width.
`layout="split"` paints a colour-set ground over the whole top panel (the showcase-showcase shift: `tone` cream, dark,
tan, accent, all mixed from brand.json); `card` / `stage` draw on the paper stage (cream set); `full` draws over the
full-frame speaker (`face=(x, y, h)` keeps type off the face).

| id | what | key fields | fits |
|---|---|---|---|
| `title-stamp` | huge serif headline stamps in letter by letter on its word, optional `≠` / italic sub-line, colour-set shift | `text`, `sub`, `neq`, `land`, `sub_at`, `tone` | split-deck top, motion-editorial stage, full-frame band |
| `money-counter` | the number rolls, slams on its word, steps to the next number ($15B to $60B), bars grow, context line | `steps=[[n, '@word']]`, `prefix`, `unit`, `kicker`, `label` | split top, stage, full band |
| `cycle-chart` | a line draws through labelled phases (plateau then cliff, dip / bottom / recovery, rise), stopwatch, ghost curve, stamp | `shape`, `labels`, `marks`, `stamp`, `stamp_at`, `stopwatch`, `ghost` | split top, stage |
| `evidence-hero` | the study's stat slams, the chart (from the cited figure) builds, the citation card lands, a bar can ring | `kind`, `citation`, `series`, `labels`, `stat`, `stamp`, `draw` | split top, stage; needs the project's sources |
| `nle-timeline` | an editing timeline of THIS video builds (cuts, captions, graphics, waveform, SFX), playhead + running timecode, folds to a line | `title`, `land`; compiler fills `span`, `cuts`, `blocks` | split top, stage, full band |
| `fire-timeline` | an editing-timeline card chars on `ignite`, catches procedural fire on `burn` (flames, turbulence, embers, heat shimmer), drops away | `title`, `ignite`, `burn` | split top, stage, full band |
| `word-stamp` | one huge word stamped behind the head (`matte` = a cut-out) or on an in-front slab, set-up line struck through | `word`, `setup`, `strike`, `at` (the stamp word) | any full-frame style with a cut-out; slab elsewhere |
| `palette-fan` | swatches fan out like a paint deck (live thumbnails, colour chips, names along the strips), the pick lifts | `label`, `fan_at`, `pick_at`, `pick`; compiler fills `items` | split top, stage |
| `video-card` | a course card unfolds: a vertical player of the creator's own reels, the title and a chapter list; play presses on the word, each chapter arrives and lights on its word, the scrubber fills, it folds | `title`, `chapters`, `play_at`, `chapter_at`; compiler fills `clips` | split top, stage, full band |
| `grid-collapse` | the frame shrinks into the centre of a 3x3 grid, eight tiles pop, fall away, you snap back | `pop_at`, `cue`; compiler fills `tiles` | full-frame beats (split-deck uses a full beat) |
| `magazine-cover` | the frame becomes a cover: rules, masthead letter-drop, coverlines beside the head, barcode, sticker | `mast`, `lines`, `kicker`, `sticker`, `lines_at`, `sticker_at` | full-frame beats |
| `reel-orbit` | the creator's own reels orbit them in depth (front over, back under the cut-out or fading behind the head) | compiler fills `media`; `spin` | full-frame beats |

```python
k = rrkit.Kit.for_split(cx, beat)                       # or Kit.for_stylekit(proj) / Kit(brand, words)
p = k.cycle_chart(shape="drop", labels=["barrier to entry"], marks=["@barrier"], stamp="plummeted",
                  stamp_at="@plummeted", stopwatch=True, tone="dark")
html = rrkit.mount(cx, p)                               # same mount() as every kit piece
import hero_schema; hero_schema.validate("cycle-chart", args, line, context, sources)   # None = usable
```

**Compiler path** (`engine/compile/`): a hero beat asks `hero_lib.ask` (llm_router.typed, cheap chain, the catalogue
+ the idea + the line) for `{"hero": id | "none", "args"}`; `hero_schema.validator` rejects invented words or
numbers, anchors outside the line, unknown fields and citations not in `script.md` / `work/sources.txt`; the compiler
adds the data a model never writes (`hero_lib.data_for`: real cuts for nle-timeline, stills of the creator's own
footage or `assets/reels/*.jpg` for orbit / grid / palette). No fit -> the kit fallback as before. The split adapter
writes `{"insert": "hero", "args": {"comp": id, ...}}` (`kit_insert.hero` fills layout, area and the face), a
split hero borrows the caption-only lines before it in its section when its line is short (`compile/rich.py`), and
every split panel gets a section colour set (`rich.section_tones`) with an editorial meta row (the brand handle and a
rule) and a faint grid: words become `title-stamp`, numbers `money-counter`, lists / typer / CTA sit on a `ground`.
Caps (2026-10-13): at most 4 title-stamps per reel (`rich.TITLE_STAMP_CAP`: the hook, hero beats, payoff and
proof lines win; the rest become the calm word card on the ground) and up to 5 hero moments per reel
(`plan_schema.MAX_HEROES`). The planner's stage A sees the catalogue and may name a `library` id per hero moment.
The creator's own reel thumbnails feed grid-collapse, reel-orbit, video-card and palette-fan: `<project>/assets/reels/*.jpg`,
else brand.json `reels_dir`, else stills of the A-roll.

Rules: one hero per beat; heroes that copy the plate (`grid-collapse`, `video-card` default clip, `word-stamp` /
`magazine-cover` / `reel-orbit` with a matte) stay inside one shot and want camera `still`; a matte must play in
composition time (`matte_start` = the cut second of its first frame).
