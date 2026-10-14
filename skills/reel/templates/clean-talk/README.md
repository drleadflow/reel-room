# Clean Talk

You, full frame and natural. One white word at a time at chest height (soft shadow, no box). A small 3-line headline
opens the reel (middle line in the emphasis color), one or two typography moments put a big keyword in the emphasis
color on the spoken word (captions step aside while it shows), and one or two small rounded cards land in the free space
above the shoulders, then clear. Gentle push / pull zooms across whole phrases, framing changes only on cuts. Voice only.

Runs on the split engine (`templates/split/compose.py` + `gallery.py`); this folder adds the inserts, the caption look
and `ctqa.py` (eyes-on sheets). Plan every beat first (`out/<style>/beats.json`): one focus per beat, never headline +
card + typography at the same time, presenter-only is a valid beat.

## Setup in a project

`project.json` `"style": "clean-talk"`, every `edl.json` segment `"mode": "full"`; give same-framing jump cuts a
`"punch": 1.12` (or start a `ct_push` above 1.0 on the cut). Overlays (time anchors: `"@word"`, `"@word:2"`, `"#cut"`, s):

```json
"overlays": [
 {"insert": "ct_push", "from": 0, "until": "#cred1", "args": {"seg": "hook", "s0": 1.0, "s1": 1.04}},
 {"insert": "ct_headline", "from": 0, "until": "#cred1", "args": {"lines": ["5 Things I'd Do", "To Get In Shape", "As Fast As Possible"], "em": 1}},
 {"insert": "ct_card", "from": "@I'm", "until": "#n1a", "args": {"side": "left", "w": 600, "kicker": "Your Name",
   "rows": [{"text": "Physician", "at": "@physician"}, {"text": "Health coach in residency", "at": "@health"}]}},
 {"insert": "ct_type", "from": "@Number", "until": 14.62, "args": {"hide_until": "#n1b", "lines": [
   {"text": "Number 1, I would start with", "at": "@Number"}, {"text": "Blood Work", "at": "@blood", "big": true}]}},
 {"insert": "ct_lab", "from": "@fasting", "until": "#n1e", "args": {"side": "right", "kicker": "Fasting insulin", "unit": "µIU/mL",
   "threshold": "7", "slide_at": "@over", "mark_at": "@7", "flag": "Insulin resistance", "flag_at": "@means"}}
]
```

| insert | what |
|---|---|
| `ct_headline` | 3 stacked lines (strings or `{"text", "at": "@word"}`), `em` = index in the emphasis color; lines push up through a mask (frame 0 already part-risen), the gold line sweeps in from the left with a soft blur; fast exit before `until` |
| `ct_type` | small connecting lines + one `big` keyword line; small words snap up on their spoken words, the gold keyword stamps in letter by letter (2 frames apart) and leans 6 % toward the viewer while it holds; captions hidden from `from` to `hide_until` (default `until`); `hold: true` keeps it to the end |
| `ct_card` | swings in with depth (3D tilt from its side, blur, small overshoot), floats while it holds; rows grow in on their words: tick pops and draws, text pushes up through a mask |
| `ct_lab` | same depth entrance and float; marker slides past the threshold and squashes on arrival, the high zone floods in, the threshold number stamps, the flag pops |
| `ct_push` | gentle push / pull of the speaker about the face (`work/facepos.json` of `seg`), scales stay >= 1.0, reset on `until` |

Any of `ct_headline`, `ct_type`, `ct_card`, `ct_lab` takes `"section": "#seg"` (or a list): that cut opens a new
section (hook to credentials, item 1, item 2), so the engine motion layer may give it a transition. Clean Talk keeps
them calm: the move set is narrowed to zoom-through / circle reveal (never a whip) unless `project.json` motion.transitions
names its own moves. Camera settle / punch / reframe come from the engine motion layer (`references/motion.md`).

## Look decisions (tested on the sample's real frames, 390 px wide)
- Emphasis `#F2CF7A` (warm gold) over white text with a 3-layer soft shadow. Oxblood as the headline emphasis went muddy
  against the bright ceiling/wall under the shadow; dark ink + oxblood read fine but lost the clean white look.
  Oxblood stays the secondary: card kickers, ticks, the lab marker and flag (on white cards it reads perfectly).
- Captions 76 px Inter Tight 800, white, the same soft shadow (holds up over a white shirt and the black mic), top =
  tracked chin + 34 px, clamped 1236-1370. `captions.no_repeat` is off: `ct_type` hides captions itself.

## Build
```
PY SK/templates/split/facetrack.py P                 # once per A-roll
PY SK/templates/split/gallery.py P OUT                # compose, lint, render, master, demo/loop/poster, styleqa
PY SK/templates/clean-talk/ctqa.py P OUT/demo.mp4 OUT/qa --times 2.4,13.9   # eyes-on sheets + peaks
```
