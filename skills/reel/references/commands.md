# Exact commands and checks

`PY` and `SK` are defined in SKILL.md. `P` is the project folder. Every path is absolute and quoted.

## Names before ingest

Whisper mishears names and brand words. Ask the user once: "Any names, brands or product words I should spell right?" Write one per line to `~/.reel-room/names.txt` (all projects) or `P/names.txt` (this reel). Do this before `ingest.py`. Later mishearings are fixed with `words.py fix` (below).

## Script directions

If the user has a script, save it as `P/script.md` before planning beats, then `PY SK/engine/script.py P`. It writes
`P/work/directives.json` (one item per direction, cut-time `t0`/`t1`, flags). Grammar and how to turn items into beats:
`references/script-directives.md`. Re-run after assemble and after every snip round (times move).

## Takes, false starts, joins

- Unclear take boundary or possible false start: `PY SK/engine/splice.py P env <clip> <t0> <t1>` prints the energy envelope for that stretch of source time. Read it. Speech shows as a run above the floor, a restart shows as a short burst, a gap, then the real line.
- Once you have checked an edge by ear and envelope, set `lock_in` or `lock_out` on that EDL segment so `snap` leaves it alone.
- `snap` never moves an edge more than 0.6 s. When a move would be bigger it prints `WOULD MOVE` and leaves the edge: look at it yourself (`env`), pick a better in or out, or change the take. Locked segments show `note (locked)` in the audit, not `FIX`. After you have listened to a note and it is fine, silence it in `project.json` with `"segments_ok":[{"id":"n1a","why":"listened, clean"}]`.
- `splice.py P joins` gives the verdicts (energy plus text). Fix flagged joins. Waive one only when you have confirmed the audio is fine, by adding to `project.json`: `"joins_ok":[{"a":"n1a","b":"n1b","why":"deliberate breath, listened"}]`. Never waive to make QA pass.

## Captions (words.json)

Captions default to the EDL `line` text aligned to the measured word times. So `line` in `edl.json` must be EXACTLY what was said in that take: verbatim, with every word kept, including false-start words you decided to keep. Write it from what you heard, not from what the script intended. House style is numbers as digits ("5 things", "Number 1"), so write `line` that way.

Whisper-only mode (captions straight from the transcript, no `line` text): set `project.json` `"captions_from":"whisper"`.

1. After `assemble.py`, build: `PY SK/engine/words.py P build`. `assemble.py` already ran the full medium.en pass on the final `assets/aroll.mp4` (that is why it takes about 45 s on a 1-minute clip). `build` reuses that pass, aligns the `line` text to the word times, writes `words.json`, then re-applies `caption_fixes.json`.
2. Read `words.json` and compare with what was said. Fix each mishearing: `PY SK/engine/words.py P fix "<wrong>" "<right>"`.
   - If the pattern has punctuation, it matches that exact token (`"gym."` only matches `gym.`).
   - It prints every place it changed.
   - `--at <sec>` changes only the occurrence at that cut time.
   - If the pattern matches more than once it refuses; add `--at <sec>` for one, or `--all` for every match.
   - Fixes are saved in `P/caption_fixes.json` and re-applied on every rebuild, so a snip round does not undo them.
     A fix made at a cut time (`--at`, `pin`, `time`) also stores its source moment (`src`) and follows the cut when a
     snip or nudge moves it; if that moment was snipped out, the build says the fix was skipped.
3. Timing: Whisper sometimes starts a word late (the first word after a cut) or ends it early, so the caption appears
   after the word is heard or a cut-off caption leaves speech uncaptioned (`gap_audit` caption gaps). Read the energy
   (`splice.py P env` or the master RMS), then `PY SK/engine/words.py P time <word-time> <start> [<end>]` (text unchanged,
   saved in `caption_fixes.json`, re-applied on every build). A word that starts a few frames before a cut but belongs to
   the next segment's line moves into that shot this way. `project.json` `"captions": {"hold_gap": 0.7}` keeps a caption up
   through short pauses instead of blinking off.
4. Never hand-edit `words.json`. It is regenerated.

## Inserts and hook

Top-panel inserts, the `top` field in `edl.json` and the `beats` list in `project.json` are described in `references/inserts.md` (written by the template side). The hook is `project.json` `"hook": {"l1","l2","category"}`: 2 lines, 2 to 4 words each, ALL CAPS, category from `hook-school.md`. Every `edl.json` segment can carry `top` (what shows in the top panel for that segment).

## Build order

```
PY SK/engine/assemble.py P                       # ~45 s on a 1-min clip: it also runs the medium.en caption pass
PY SK/engine/headpos.py P
PY SK/engine/words.py P build                    # reuses assemble's caption pass, so it is fast
PY SK/templates/split/render.py lint P          # composes first, then runs npx --yes hyperframes@0.8.34 lint, must be 0 errors
PY SK/templates/split/render.py P               # compose, lint, render -> prints the output path
PY SK/engine/deliver.py P P/renders/<slug>-vN.mp4          # master, share + silent (sized to fit 19 MB), review (<15 MB), voice, cover, srt, and P/room/downloads.json (local paths: upload each, swap in the asset url, write downloads/files)
PY SK/engine/qa.py P P/renders/<slug>-vN-master.mp4        # QA runs on the MASTER
```

Motion v2 is part of compose (no extra command): `project.json` `"motion"` sets the level and the SFX density
(`references/motion.md`). Compose writes `work/motion_plan.json` (camera, transitions, events); render mixes the SFX
on those events under the voice (`work/motion_sfx.json`, stem `work/motion_sfx_stem.wav`) and keeps the voice-only
render. Render prep runs `engine/hdr.py` on every video the composition loads (log `work/hdr_fix.json`); run it by hand
with `PY SK/engine/hdr.py P`. Motion gates alone: `PY SK/engine/qa_motion.py P <master> [--level polished]`.

`render.py` renders SDR with screenshot capture (`--sdr --experimental-fast-capture=false`): an iPhone HLG A-roll would
otherwise switch HyperFrames to its HDR layered composite, which paints the videos over every caption and card. If a
render ever looks different from `render.py snap`, check `renders/.render.log` for "HDR" first.
`render.py` picks the next free vN across `renders/` and `work/`. Always use the path it prints, never guess `vN`. Order is render, then deliver, then QA on the master. Never show a round before QA passes. A QA fix means changing the cause and going back to render.

Cover candidates (for the Room's cover picker): `PY SK/engine/deliver.py P P/renders/<slug>-vN.mp4 --cover-options 6`. Covers only, about 3 s, never touches the master. You get 6 clean frames (open eyes ranked first) plus 2 hook-title composites (8 files in all) (the title card placed on a clean frame). Upload the PNGs as assets and write `cover/options`.

Other render helpers: `render.py P --safe` (draft with safe-zone guide), `render.py snap P <t> ...` (stills at cut times).

### Face fixes (headpos)

Haar misses profiles (the speaker facing a board) and sometimes fires on a hand or a poster. After looking at the
frames, pin a segment in `project.json`: `"face_fix": {"a2b": {"cx": 300, "cy": 705, "h": 150}}` (aroll pixels). `headpos.py`
applies it after detection on every run (marked `"fixed": true` in `work/facepos.json`). Never guess one without looking.

### Sound cues (only when the user asked for SFX)

File SFX on exact cut times go in `project.json` `"sound": {"cues": [...], "muffle": [...], "sfx_until": s, "ticks": {...}}`
(fields in `templates/split/soundcues.py`). `render.py` mixes them under the voice after the render (voice never
filtered: a muffle window low-passes the SFX bus only), keeps the plain voice render as `<slug>-vN-voiceonly.mp4`, and
writes `work/sound_report.json`. `deliver.py` then also writes `<slug>-vN-voiceonly-master.mp4` and takes the voice-only
audio from it; `gap_audit` measures pauses on that voice-only master. Check the mix without playing it:
`PY SK/templates/split/soundcues.py P /tmp/mix.wav` prints LUFS, true peak and the SFX peak.

## Reading qa/cut_check.jpg

It is a strip with a before frame and an after frame for every cut. The `cut_shots` check reports per half: the speaker half and the top panel are judged separately, and a cut passes when at least one half shows a clearly new picture on its first frame. So:

- A split to full (or full to split) cut changes the speaker half. Fine.
- A same-layout cut (split to split) needs something new in the top panel. A top-panel entrance (new insert, B-roll, card landing) on that cut is expected and is what makes it read as a cut.
- If `cut_shots` names a cut where neither half changed ("barely changes"), change the layout or give that segment a new `top` insert, then re-render.
- If it names a cut "landing a frame late", the new shot arrives a frame after the cut: check the entrance timing for that beat.

A good strip:

- Every after frame is clearly a NEW shot (speaker half or top panel).
- No half-faded or blended frame, no duplicated frame (after identical to before), no black frame.
- The face is visible and not covered, captions are not mid-swap.
- The first frame of each cut already shows the new shot (not the old one for a few frames).

## Motion QA checks (qa.py, from engine/qa_motion.py)

Ten gates run with the others (names, labels and thresholds: `references/motion.md` section 6): `motion_density`,
`dead_frames`, `event_density`, `hdr_alpha`, `ease_lint`, `hero_scale`, `sfx_sync`, `behind_head`,
`transition_budget`, `motion_strips`. Targets follow `motion.level` (simple is exempt from the density gates).
Metrics, the per-second sparkline and the still stretches are in `qa/motion.json`. A dead stretch is fixed with a real
move on that phrase (a graphic that builds, a reframe, a stronger hero), or `"motion": {"still_max": 1.5}` when the
user wants a calm moment and says so.

## New QA checks (qa.py)

- `list_rules`: only when the style wrote `P/work/list.json`, else "not applicable". Numbers fixed across reveals,
  active row highlighted, list gone after `clear_at`, even row gaps. Shape in `engine/qa_extra.py`. A horizontal list
  (numbered slots side by side) writes `"axis": "row"`: numbers must share one row and the slots be evenly spaced in x.
- `new_shot_captions`: first 3 frames of every new shot and of its first caption. The face is found in the rendered frame
  (planned face box as fallback). A caption on the face or on other on-screen text fails with the cut, time and frame,
  and saves `qa/new_shot_f<frame>.jpg` with the boxes drawn. Look at it.
- `gap_audit` (runs last): the final master audio (RMS) plus captions. Reports pauses over 0.35 s (even when a caption
  hides them), speech with no caption on screen, clips under 0.4 s with no words, voice running through a cut (clipped
  syllable). Full list `qa/gaps.json`. It never fixes anything. For each finding: trim it (snip, nudge, or split the
  segment around an inner pause, a new cut needs a layout change or new insert), or keep it on purpose after listening:
  `project.json` `"gaps_ok":[{"t":15.24,"why":"breath before the number, listened"}]`. Never stretch captions to hide
  a gap, never cut part of a word. Thresholds: `project.json` `"gap_audit":{"max_pause":0.35,"min_clip":0.4,"tail_max":0.8}`
  or `qa.py ... --max-pause 0.4`. Run one check alone: `qa.py P <master> --only gap_audit`.

- `text_collision` (`engine/textcheck.py`): headless Chrome seeks the composition every 3 frames and measures every
  visible text element per character: overlap (more than 6% of the smaller line box), a headline that wraps, an orphan
  (a 4+ word block ending on a one-word line), overflow past the frame or its clipping panel, word gap under 0.18em,
  letter-spacing under -0.03em, negative word-spacing, two captions at once. A finding must hold for 8 samples in a row
  (tracking, word-spacing and two captions count at once). Gaps are judged in on-screen ems and corrected for tilted
  cards. Fix spacing with CSS `word-spacing` / `letter-spacing` (display type no tighter than -0.03em), never by
  loosening the gate. Skipped without index.html or Chrome. Report `qa/textcheck.json`. Strict pass before delivery:
  `PY SK/engine/textcheck.py P --step 2 --persist 3`. About 1 to 7 s per reel.
- `caption_phrasing` (`engine/capcheck.py`): from layout_boxes.json captions. Fails when a caption ends on a binding
  word (to, of, the, per, ...) or splits a number from its unit while the next one follows within 0.4 s, when captions
  overlap in time, or on a one-word caption squeezed between others (not in word-by-word styles). Breaks between
  different segments (`seg`) or on a cut are forced by the edit and allowed. Report `qa/capcheck.json`.
- `aroll_repeats` (`engine/aroll_fix.py check`): repeated frames the cut added, measured against the same window of
  the source (source stills never count). assemble.py fixes these itself (below); this gate catches an aroll made
  another way. Skipped without sources.json or the source clip.
- All three live in `engine/qa_more.py` and run with the rest; one alone: `qa.py P <master> --only text_collision`.

## Showcase tools (ported from the showcase showcase, 2026-10-13)

```
PY SK/engine/aroll_fix.py P [--check] [--json]     # repeated frames from assemble's seek + fps step
PY SK/engine/textcheck.py P [--step 3] [--persist 8] [--out FILE] [--json]
PY SK/engine/capcheck.py P [--out FILE] [--json]
PY SK/engine/showcase.py copy <master.mp4> SK/styles/showcase/<reel>-<style>.mp4 [--poster-from IMG | --poster-at S]
PY SK/engine/showcase.py check SK/styles/catalog.json
PY SK/engine/showcase.py doc SK/styles/catalog.json P/work/showcase_assets.json    # -> the styles/examples db doc
PY SK/engine/cutout.py P --engine birefnet [--quality fast|balanced|best]          # opt-in matte, see below
```

- aroll_fix: assemble's `-ss <in> ... fps=30` can repeat the first frame of a segment (a hitch on every cut) or every
  third frame on some sources. assemble.py now measures this right after it writes segments.json and, when the cut
  added repeats, re-cuts every segment with the same crop, zoom and grade but no fps step (seek half a frame early,
  exact frame count, passthrough), copies the aroll audio back, and keeps the result only when the frame count matches
  and it has fewer repeats. Log line: `repeated frames: 5 added by the cut -> 0 (fixed)`. Off: `project.json`
  `"aroll_fix": "off"`. Sources outside 29.9 to 30.1 fps are left alone (they need the fps step).
- showcase.py: review copies for the Room's "On real reels" (720x1280 H.264, AAC 128k, faststart, under 12 MB, poster
  jpg). `check` verifies every catalog example; `doc` builds `styles/examples` (room-protocol.md "Showcase examples").
- cutout `--engine birefnet` (opt-in, `engine/matte_birefnet.py`): BiRefNet HR-matting, MIT. `auto` still means
  hyperframes, then rembg. On a 2 s test clip it was clearly cleaner than hyperframes (no blue-grey sky halo around the
  head and shoulders, no background specks) but about 6x slower: about 1 fps at `--quality fast`, 0.4 to 0.8 fps at
  `best` on Apple Silicon (a 77 s reel at best is roughly 50 to 100 min plus a few minutes of finalize). Not yet
  tested on long hair, so the default stays. `--quality`: fast 1024x576, balanced 1536x864, best 2048x1152 model input.
  It runs in its own Python with torch + transformers, found in this order: env `REEL_ROOM_BIREFNET_PY`,
  `~/.reel-room/platform.json` `"birefnet_py"`, `~/.reel-room/birefnet/bin/python`. One-time setup:
  `python3 -m venv ~/.reel-room/birefnet && ~/.reel-room/birefnet/bin/pip install torch transformers timm kornia einops pillow numpy`.
  Model cache `~/.reel-room/models/hf` (first run downloads about 450 MB, or `matte_birefnet.py seed-cache <hf dir>`);
  `matte_birefnet.py check` shows the Python and the cache. Edge cleanup in the venv: temporal median where the plate
  is still, 1 px choke, 0.8 px feather, blur-fusion colour decontamination, despill. Progress in
  `work/cutout.status.json` (stage infer/finalize, percent, fps, eta_s); crash safe, it resumes from
  `work/matte_alpha/` (FFV1 parts of 150 frames).
- Light SFX mixer: `mix_lite.py` was not ported. It uses this engine's own `motion/mixer.py` helpers
  (same 18 dB floor, same peak-on-the-event alignment, same LUFS math). What it adds: a hand-written cue list
  (`work/sfxlite.json`: time, sound FILE, its own dB under the voice, offset, duration), ducked beds with a level curve,
  an optional music bed N dB under the voice with fades, and a remix onto an existing render (video stream copied, no
  re-render). The engine's `light` mode picks sounds automatically from motion events (at least 1.5 s apart, at most 3
  per 10 s, 20 to 22 dB under). For "exactly these 5 to 8 sounds" or "add music without re-rendering", that script is the
  reference; port it as a `remix` command when it is needed in the engine.

## Repurpose a posted reel (engine/repurpose.py)

For an already-posted reel (a downloaded 720p or 1080p file) with the old title, captions and cards burned in. The old
text must never show under the new style: hide it by layout (crop) or cover it fully.

1. Detect: `PY SK/engine/repurpose.py detect "<download.mp4>" --out "P/work/repurpose.json" --sheet "P/work/repurpose_sheet.jpg"`.
   It proposes regions: static titles in the top 30% (with frame windows, a title on a pill gets the whole pill), the
   caption band with per-frame x extents (`per_frame`), and dark or light cards, each with a method: `inpaint` (glyph
   mask incl. outline and shadow, flat walls), `ref` (clean frames of the same locked-off shot), `interp` (pills, flat
   panels), `blur` (cards, the caption band).
2. LOOK at the sheet and fix the json by hand: boxes are SOURCE pixels `[x0,y0,x1,y1]`, `frames` inclusive source frame
   numbers or "all". Add what it missed (lower thirds, a second caption band) from the `todo` example; `detect ... --redraw`.
3. Test bake a window and look at every tile of the check image before the full bake:
   `PY SK/engine/repurpose.py bake "<download.mp4>" "P/work/repurpose.json" "P/assets/plate_clean.mp4" --frames 0-240 --check "P/work/repurpose_check.jpg"`.
   If a letter still reads, grow the box, switch method (`blur` hides anything) or widen `frames` over the fade. Then
   bake without `--frames` (H.264 CRF 15, bt709, source audio).
4. Ingest the plate as the clip (`ingest.py P "P/assets/plate_clean.mp4"`), normal build. New captions and titles must
   sit over the soft caption bar and any card blur. Record `project.json` `"repurpose": {"src", "regions":
   "work/repurpose.json", "plate": "assets/plate_clean.mp4"}`.
Hide by layout instead: `PY SK/engine/repurpose.py crop "<download.mp4>" "P/work/repurpose.json"` prints the largest
9:16 crop that keeps the title and caption bands out as `zoom`/`cx`/`cy` for edl.json, plus the upscale factor (cards in
the middle are listed "uncovered"; above about 2x from 720p the picture goes soft). Tests: `tests/test_repurpose.py`.

## Storyboard approval hash

The page records `storyboard/approval.for` as a hash of `storyboard/current.beats` (djb2 over `JSON.stringify(beats)`, base 36). Do not compute it by hand. Use the engine:

```
PY SK/engine/hash.py P                  # prints the hash of P/work/storyboard.json beats
PY SK/engine/hash.py P --write          # also writes room-sim/storyboard/approval.json (fallback mode)
```

Always save the beats you send to `P/work/storyboard.json` (leave out keys a beat does not use). The hash sorts every object's keys first, in `hash.py` and in the page, because the db can return keys in a different order. Build is allowed when `storyboard/approval.ok` is true AND `for` equals the printed hash. A different `for` means the beats changed since the user approved: ask again. Do not assemble on a stale approval.

Fallback note (only if `hash.py` is missing): run this by hand, with `P/work/storyboard.json` holding `{"beats":[...]}`:

```
PY - <<'PYEOF'
import json
b = json.load(open("P/work/storyboard.json"))["beats"]   # replace P with the real absolute path
s = json.dumps(b, separators=(",", ":"), ensure_ascii=False)
u = s.encode("utf-16-le"); x = 5381
for i in range(0, len(u), 2):
    x = ((x << 5) + x + (u[i] | (u[i + 1] << 8))) & 0xFFFFFFFF
d = "0123456789abcdefghijklmnopqrstuvwxyz"; out = ""
while x: x, r = divmod(x, 36); out = d[r] + out
print(out or "0")
PYEOF
```

## Rounds, motion levels and go-back (rounds.py)

```
PY SK/engine/rounds.py P snapshot --round N        # after QA passes, before publishing round N (archives every beat)
PY SK/engine/rounds.py P index --json              # -> rounds/index doc for the Room
PY SK/engine/rounds.py P apply P/work/room_motion.json --json   # motion/choice + motion/beats + beat_changes
PY SK/engine/rounds.py P use <seg> <round> [--timing]   # one beat back to round N (look; --timing also the take)
PY SK/engine/rounds.py P simpler <seg>             # one level down (showreel > polished > simple)
PY SK/engine/rounds.py P level <seg> <simple|polished|showreel|reel>
PY SK/engine/rounds.py P reel-level <level>        # project.json motion.level
PY SK/engine/rounds.py P beatmap                   # storyboard beat -> segments (work/beat_map.json, set "manual": true to fix by hand)
PY SK/engine/rounds.py P list | diff <a> <b>
```

- Archive: `P/rounds/r<N>/` (edl, project, segments, words, storyboard, per-beat `beats.json`) plus `P/rounds/blobs/` (every
  file a beat references, stored once by content). A restored file that changed since lands in `assets/rounds/r<N>/`;
  current files are never overwritten.
- Levels become segment overrides the motion planner already honours: simple = `transition:none, camera:still`;
  showreel = a cycled move + `camera:push`; polished under a showreel reel = `transition:none`, under a simple reel =
  `transition:push`. Each segment also carries `motion.level` and `from_level` (which keys the level set).
- Every look change is logged in `work/beat_looks.json`; `snips.py undo` re-applies it after rebuilding the EDL.
- `apply` prints `rebuild`: `render` (compose, render, deliver, QA; skip assemble, headpos, cutout), `assemble`
  (timing moved: the full build), or `nothing`.

## When the Artifact tool or db is not available

Run the same flow with files and chat:

- Share the review copy as a file: give the user the path of `renders/<slug>-vN-review.mp4` (or open the folder for them). Do not play audio through the speakers.
- The user sends notes by pasting the "Copy notes for Claude" text, or typing them. Read it like the db docs.
- Keep the same state model in `P/room-sim/` as JSON files mirroring the db paths: `room-sim/storyboard/current.json`, `room-sim/storyboard/approval.json`, `room-sim/review/current.json`, `room-sim/notes/<id>.json`, `room-sim/snips/<id>.json`, `room-sim/caption/current.json`, and so on. Write to them exactly where you would call ArtifactData, and read from them where you would read the db. Add the user's pasted answers (approval, choices, notes) as docs there.
- Everything else (QA, rounds, snips, hook, caption, post confirmation in chat) is unchanged.

## Vision judge (taste QA)
`judge.py <clips...> [--kind hero|reel] [--intent "..."] [--ref REF] [--strong] [--out FILE]`
- A video model watches each clip (shrunk to 540 px / 12 fps) and returns a typed verdict on six criteria: readable, on_word, premium, face_clear, motion, purpose. Every failure gets a timestamped issue plus a fix. Clips run in parallel. Exit 0 only if all pass. Needs OPENROUTER_API_KEY.
- Prefer `--ref`: pairwise "worse / same / better" against a reference that sets the bar (e.g. `<a reference reel>.mp4`). Absolute 0-10 scores cluster around 6 and do not separate plain work from premium work.
- `--strong` uses Gemini 4 Argon first (about $0.04 per reel); the default fast chain costs about $0.005 per clip. Use the fast chain while iterating and `--strong` for the final pass.
- The judge covers taste (readability at phone size, timing to the word, premium look, visual bugs). Exact rules stay in qa.py.

## Plan to reel in one run (engine/pipeline.py, 2026-10-13)

```bash
PY SK/engine/pipeline.py P --style editorial-ui --plan-fresh --brief "..."   # or --style split-deck
```
- t=0: `cutout_cache.py run P --follow` starts as soon as `assets/aroll.mp4` exists (editorial-ui only), while
  `plan_fast.py` + `compile_plan.py` run; compile writes `work/cutout_need.json` (set cuts + behind-head hero spans) and
  the worker then skips every other frame. The render waits for the worker (never next to it on a shared machine).
- Cut-out cache: `P/work/cutout/<model>-<aroll hash>/m*.png` (320 px masks, u2net_human_seg on the Neural Engine + a
  CPU session). A new plan never recomputes a frame; a re-assembled A-roll gets a new folder.
- editorial-ui bake cache: `P/work/bake_cache/<aroll hash>/`, one chunk per cut (room chunks once per A-roll, set
  chunks per look), joined with a stream copy. `compile/runner_eui.py final P` = compose (bake) -> lint -> render
  (6 workers) -> master + voice-only (one video encode) -> template QA and engine `qa.py` side by side.
- Measured on the EDIT reel (62 s, M4 Pro, machine load 20 to 70): editorial-ui re-plan 3:53 to 4:31, first run on new
  footage (cold cut-out + cold bake cache) 4:44 to 6:18; split-deck 2:37 to 2:42. Timings: compile-test/timing.json.

## On-screen numbers are verified against the audio (engine/numcheck.py, 2026-10-14)

Medical content: a misheard number ("16 billion" for "$60 billion", "0.4" for "0.24") must never reach the screen.
```
PY SK/engine/numcheck.py P [--no-llm] [--force] [--json]     # pipeline.py runs it before compile
```
- Every number in the captions (words.json) and the EDL lines gets a second medium.en reading of a small window with
  a numbers prompt, then a cheap model compares both readings in context (typed `{agree, value, confidence}`).
  Verified = reading B says the value and the model agrees with confidence >= 0.8. No key / `--no-llm`: verified
  "speech only" (lower confidence, `"check": "speech_only"`) when reading B says exactly that value on the word.
- Anything else is BLOCKED: removed from the captions (backup `work/words.prenum.json`), shown words-only or dropped
  in graphics by the compiler (each change is a compile note), listed in `work/number_flags.json` for a human.
  Confirm one after listening: `project.json` `"numbers_ok": [{"value": "7", "t": 21.8, "why": "..."}]`, re-run.
- Ledger `work/numbers.json`. compile_plan fails loudly when an unverified number would still be on screen (or when
  graphics carry numbers and numcheck never ran). QA gate `numbers_verified` (qa_more.py, numgate.py) re-checks the
  final project: captions, set headlines, cards, heroes, split inserts, hook. Evidence-hero data may also come
  verbatim from `work/sources.txt`.

## editorial-ui data heroes (compile/eui_data.py)

money-counter and evidence-hero go on their own colour set (cut-out on a plain plate, punch-in 1.0) in the band above
the head, never over the face (kitcards.above_band). Optional rows are dropped until the hero fits the band
(work/facepos.json); no room, a cut too short, or an evidence citation not in `work/sources.txt` -> the closest
treatment (ed-number, a SOURCE status pill, the anchor word). title-stamp becomes a set headline (4 at most, hook
included); heroes stay capped at 5. Every substitution is a compile note (`project.json` `compiled.notes`).

## CPU budget (engine/rrlimits.py)

`RR_MAX_THREADS` (env) or `project.json` `"machine": {"max_threads": N}`; default half the cores; `off` = uncapped.
Every ffmpeg / ffprobe call gets `-threads` (common.ffmpeg, ffmpeg_bin(), and a PATH shim in `~/.reel-room/shim` that
also catches direct `"ffmpeg"` subprocess calls and runs them under nice 10); onnxruntime sessions get intra/inter op
limits; render workers, bake and assemble pools follow the budget (parallel ffmpeg jobs split it); OMP/BLAS env vars
carry it into children. pipeline.py prints the peak load of its run (`"load"`: load1_peak, tree_cores_peak).
`common.nice_prefix()` is `["nice", "-n", "10"]`, or `[]` on Windows.
