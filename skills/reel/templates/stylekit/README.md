# stylekit

Shared plumbing for the full-frame style templates (`floating-cards`, `carousel-slideup`, `desk-demo`). Ours, clean-room.
It reuses the split template's `theme.py` (brand + fonts), `measure.py` (headless Chrome) and `render.py` (pinned
HyperFrames lint/render) and the engine's `deliver.make_master` read-only.

## One command

```
PY SK/templates/stylekit/build.py <project> --out <dir> [--no-render] [--qa-only]
```

`<project>/project.json` names the template (`"template": "floating-cards"`) and holds its content in `style_cfg`.
The build: compose (prepares the base video first) -> lint (0 errors) -> render -> sound -> `demo.mp4`, `loop.mp4`,
`poster.jpg` -> QA (`<dir>/qa/report.json` + contact sheets). Exit 1 when any check fails.

## Motion v2

`kit.build_html` wraps the speaker video (`id="aroll"` or `"base"`) in `#mvT > #mvCam`, plans the camera rig and the
transitions from `segments.json` (jump cuts are budgeted, scene cuts are section cuts; the camera grows the head
from the chin and is capped at 4.5 % because captions and cards hang right off the face), adds kinetic caption entrances
for every `[data-box="caption"]`, swaps entrance eases (`TL.fromto`) and writes `work/motion_plan.json`.
A template can steer the planner per segment (`kit._CUR["overrides"] = {seg: {"transition": "whip"|"none"}}`) and add
picture cuts it makes inside a segment (`kit._CUR["cuts"] = [{"frame": N, "transition": "whip"}]`, desk-demo cutaways).
`mix_and_master` adds the transition SFX (the template's own cues keep covering its graphics); skqa maps the face box
through the camera, skips transition frames in the switch and blank checks and appends the motion gates.

## Modules

| file | what |
|---|---|
| `kit.py` | project loading, word anchors (`"@panel"`, `"@fasting:2+0.1"`, `"@with>n2"` = first match inside segment n2), the `TL` tween emitter (every event snapped onto its frame, `fromTo` never shows its from-state early), page builder with sampling runtime (`#sample:3:N`, `#frames:a,b`, `#seek:F`), lint/render, sound pass, loop/poster |
| `behind.py` | bakes the grade and text layers BEHIND the speaker: matte refined per frame (1-2-1 temporal smoothing, static-camera clean plate removes background the matte grabbed, colour guided filter, hardened edge, 1 px erode + feather) and an edge-decontaminated composite |
| `sfx.py` | soft UI sounds synthesized from scratch: pop, pop_hi, pop_lo, thump, chime, click, swish, whoosh |
| `skface.py` | face box every 3rd frame (OpenCV Haar, band-limited to rule out shirt prints), smoothed + interpolated |
| `skqa.py` | the quality bar (below) |

## Sound

Voice is never processed: it is read from the project's voice source, mixed with the SFX cues and normalised once
(two-pass loudnorm + true-peak limiter: -14 LUFS, <= -1.5 dBTP). Every cue is levelled so the loudest 400 ms of the SFX
bus sits 20 LU under the voice's integrated loudness (QA fails under 18). Video is encoded once at ~9.5 Mbps
(35 s demo ~40 MB, under 45 MB).

## QA (`skqa.py`)

format + exact frame count, size/bitrate, loudness + SFX margin, face never covered (every 3rd frame, real transformed
boxes from the live timeline against the face track; full-frame cutaways skip), safe zone (settled readable boxes in
y 220-1470, x 35-1045, x <= 980 below y 1155), captions equal words.json in order with each caption on its first word's
frame and no orphans, no em dashes, every switch flips on its frame in the timeline AND in the rendered pixels, no blank
frames. Sheets: `switches.jpg` (N-1 | N | N+1 per event), `overview.jpg` (1 fps), `face.jpg` (face box red, boxes blue).
