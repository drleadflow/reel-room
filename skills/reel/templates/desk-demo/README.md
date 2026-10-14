# Desk Demo

Full-frame talking head that cuts to "phone filmed at the monitor" inserts, then back to the speaker for the verdict.
The screen is built in HTML (a mock portal or calendar, patient-agnostic data labelled "Sample"), shown on a monitor in
3D perspective with a dark bezel, screen glare, a soft focus, a blurred room behind and a desk below, plus handheld
micro-shake and a slow push. A cursor moves and clicks on the words (one soft click per action). Small sentence
captions (2-5 words) on a dark pill, a white native label title on the hook. Dry sound: voice plus clicks, no music.

This is the FAKED desk version (approved): no desk footage is needed. With real phone-at-monitor footage, use a video
cutaway instead.

Build: `PY SK/templates/stylekit/build.py <project> --out <dir>` with `"template": "desk-demo"`.

## project.json `style_cfg`

```json
{
 "tail": 18,
 "label": {"lines": ["5 things I'd do to", "get in shape fast"], "y": 300, "until": "seg:cred1"},
 "portal": {"app": "Lab Results", "patient": "Sample Patient", "note": "Sample data, not a real patient",
            "reports": [["Comprehensive metabolic panel", "Includes fasting insulin", "Ready"]],
            "panel_title": "Comprehensive metabolic panel",
            "rows": [["Glucose, fasting", "92", "mg/dL", "70-99"], ["Fasting insulin", "9.8", "µIU/mL", "2.6-24.9"]],
            "highlight": "Fasting insulin", "tag": "Over 7"},
 "calendar": {"month": "March", "days": 31, "first_weekday": 0, "today": 3, "pick": 26, "event": "Deadline"},
 "shots": [
  {"from": 380, "to": "seg:n1b", "screen": "list", "cam": {"focus": [520, 300], "at": [560, 820], "s": 1.25, "ry": -10, "rx": 6, "rz": -1.5},
   "cursor": {"x": 980, "y": 560}, "actions": [{"at": "@blood", "x": 560, "y": 262, "kind": "open"}]},
  {"from": "seg:n1c", "to": "seg:n1d", "screen": "panel", "scroll0": 200, "scroll": [{"at": "@make", "y": {"hl": 300}}],
   "cam": {"focus": [620, 420], "at": [520, 860], "s": 1.65, "ry": -12, "rx": 4, "rz": -2},
   "actions": [{"at": "@fasting", "x": 640, "y": 440, "kind": "highlight", "tag_at": "@insulin"}]},
  {"from": 1000, "to": "end", "screen": "calendar", "cam": {"focus": [700, 450], "at": [560, 840], "s": 1.3, "ry": 8},
   "actions": [{"at": "@deadline", "x": 812, "y": 505, "kind": "event"}]}
 ]
}
```

- `from` / `to`: a frame number (cut in a measured word gap), `"seg:<id>"` (hide a jump cut) or `"@word"`; `"end"`.
- `cam`: the screen point `focus` (CSS px on the 1200x750 screen) lands on frame point `at`; `s` scale, `ry/rx/rz` tilt.
  Each shot is a new handheld angle; `shake` (amplitude, default 1) and `push` (slow zoom) per shot.
- `scroll` y: px, or `{"hl": y}` = scroll so the highlighted row sits at y inside the page.
- Action kinds: `open` (report list -> panel), `highlight` (gold row + tag), `event` (calendar chip); every click = one
  soft click SFX, 20 LU under the voice.
- Mock data must never look like a real patient or a real company: generic app name, "SAMPLE" badge, sample note.

## Motion v2 phase 3 (`deskmotion.py`)
With the motion layer on (default), every screen cutaway is a handheld phone shot: shake + slow drift + a push toward
each clicked UI point that lands on the click (then re-steadies), a focus hunt on the first frames, a whip in (7 frames)
and out (4 frames) with directional motion blur, vertical motion blur on scrolls, a double ripple on clicks and a
spotlight that dims the screen around the row / report / day being acted on. Face <-> screen cuts get a whip from the
engine too (`kit._CUR["overrides"]` / `kit._CUR["cuts"]`); cuts hidden under a screen get none.

`style_cfg.phone`: the speaker shrinks into a phone frame over the dark room and comes back full frame on the `to` cut:
```json
"phone": {"from": "seg:n1d", "to": "seg:n1e", "in": 0.25, "scale": 0.66, "top": 250,
          "labels": [{"text": "OVER 7", "at": "@7", "x": 600, "y": 330, "rot": -5, "kind": "stamp"},
                     {"text": "= insulin resistance", "at": "@resistance", "x": 140, "y": 470, "kind": "soft"}]}
```
Per shot: `shake` (default 1.25), `push` (default 0.04); per action `push` (scale toward the click, default 1.14).
