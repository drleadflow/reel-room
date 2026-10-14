# Gotchas

Lessons from real cuts. Read before you cut, and again when a join sounds wrong.

## Splicing

**Clipped endings.** Whisper gives a reliable word START and a loose END. Cutting at "start of the next word minus a bit", or at the last word's start plus a guess, chops the final syllables. The listener hears "equipm-". A text check cannot see this, because Whisper happily transcribes a clipped "equipm-" as "equipment". Only audio measurement catches it.

**Fix.** Use the medium.en word start AND end. Put each cut inside a measured silence (energy envelope with a floor measured per clip, a hold of about 150 ms of quiet). Never inside speech, never "N ms after a word start". `splice.py snap` does this. Keep a breath in only when the user wants it natural.

**small.en drift.** The fast model drifts 0.2 to 0.4 s around pauses and drops disfluencies. Use it to find lines, never to place cuts. Place cuts with medium.en on a window of about 1.5 s either side of each cut.

**False starts.** "So I... so I started" gets transcribed as one clean "so I started". Before every in-point, check the audio just before it for a fragment or a repeated word. `splice.py audit` flags both. When unsure, move the in-point later, after the restart.

**Retakes.** The user says a line, flubs it, says it again. Take the LAST clean take, but listen for energy: later takes are sometimes flatter. Prefer the clean one with the best energy, not blindly the last.

**Text QA blind spots.** A transcript of the final cut proves the words, not the seams. These all pass a text check: clipped word endings, a swallowed first consonant, a breath in the wrong place, a click from a hard cut, a doubled word across the join. Always solo-listen each join (transcribe a 2.6 s window around it alone, and listen).

**Re-measure after every nudge.** A nudge of a few frames can land a cut inside the next word. After any snip or nudge, re-run snap or audit for the touched edges and re-check the join. Do not assume.

**Join audio.** 20 ms fade-in and 30 ms fade-out at each join, audio padded or trimmed to exactly frames/30 s. Without that, clicks appear and sync drifts over a long cut. Check the last segment's first frame lands on its frame index.

## Layout and captions

**B-roll head clearance.** The top 220 px is not safe for readable content. A 1080x960 top-panel clip with a person's head near its top edge will show the head cut off under the platform UI. Reframe or pick a different part of the clip.

**Screen recordings.** Phone screen recordings often have black or white side bars and a few looping or frozen frames at the start and end. Crop the bars out and trim the loop frames, or the top panel looks broken.

**Captions on full-frame shots.** Full-frame shots have no seam. Captions go on the chest, around y 1250, never on the face. Use the measured face box, not a guess.

**Face never covered.** Hook cards and polaroids land away from the face box. If the speaker leans in, shift the card, do not shrink the face.

**Em dashes.** None on screen and none in captions. Replace with a comma, a period or a new line.

## Motion and rendering

**HLG footage kills cut-outs.** iPhone clips are tagged HLG (bt2020). HyperFrames 0.8.34 then renders the whole
composition as HDR and drops the alpha plane of every cut-out layer: the speaker cut-out turns into an opaque frame of
the room over everything under it. Lint, check and snapshot all look fine; only the real render breaks, and `--sdr`
does not stop it. `engine/hdr.py` retags every video as bt709 (lossless) at assemble and at render prep. If a render
ever shows an opaque cut-out, run `PY SK/engine/hdr.py P` and check `work/hdr_fix.json`.

**Sparse keyframes freeze frames.** Phone b-roll can have a keyframe every 60+ frames; the renderer warns about seek
failures. `hdr.py` re-encodes those with a keyframe every 30 frames.

**One video per wrapper.** Every `<video>` sits alone in its own div. The renderer inserts each frame image as the
video's next sibling with the video's z-index, so a video next to overlay siblings stacks unpredictably.

**Coverage gate.** A timed video layer (a cut-out window, an inserted clip) gets `data-duration` = its window + 3
frames. Under 95 % coverage the renderer fails the layer.

**Motion is planned, not tweened.** The camera and transitions are keyed one frame at a time from
`work/motion_plan.json`. Never add a GSAP tween on `#mvCam` or `#mvT` by hand: it fights the keys. Use the per-beat
`motion` override instead.

**Dead frames come from the plate too.** A calm speaker in a split or card layout leaves most of the frame static.
The planner fills stills with reframes and punches only where the plate itself is still; if `dead_frames` still
fails, the beat needs a graphic that builds, not more camera.

## Files and inputs

**Photos pasted in chat are not files.** A HEIC or image pasted into the chat has no path on disk that Claude can use. Ask for the file path or ask the user to drop the file in the clips folder. Same for videos.

**The Room is not an upload box.** A video dropped or chosen in the Room's Dailies player (offline mode only) plays from the viewer's own computer. It is never sent to Claude. Clips reach Claude only as file paths in the chat. If a user says "I dropped it in the Room", ask for the path.

**HEIC and rotation.** Phone clips carry a rotation tag. Probe it and honour it, or portrait clips come out sideways. Convert HEIC stills to JPEG before use.

**Paths with spaces.** Quote every path. Expand `~` before passing it as an argument.

**Source safety.** Never move, rename or delete the originals. Work only inside the project folder.

## Posting

**Upload size.** Keep the share file under 30 MB and the review copy under 15 MB. Larger review copies fail to load on phones.

**Trial reels.** Instagram trial reels only show to non-followers first and do not appear on your grid until shared. Do not judge a trial by follower reactions.

**Custom cover.** Set the cover after picking the video. Some uploads reset it to an auto frame, so check it before sharing.

**Double posts.** If a post call times out, look at the account before retrying.

## Process

**One change at a time.** A round that changes five things hides which one broke the cut. Apply the user's notes, nothing else.

**Prove from the final file.** Extract frames from the rendered file at every join and read them. Plans and transcripts lie. The render does not.

## Showcase lessons (showcase, 2026-10-13)

- assemble's seek + fps step can repeat a frame: the first frame of a segment (a hitch on every cut) or every third
  frame on some downloaded sources. assemble.py now fixes it itself (`aroll_fix.py`); measure repeats against the
  SOURCE, because downloaded reels have their own still frames (a frozen intro is not a stutter).
- A tight display font can make a space almost vanish ("Lab panel" read as "Labpanel" at -0.02em). textcheck measures
  every word gap; fix with `word-spacing`, keep display tracking at -0.03em or looser. Card tilt and transform scale are
  taken into account; text inside a 3D-tilted screen (desk-demo monitor) is only approximate.
- In HyperFrames pages `#root` often measures 0 px tall (absolute children): take the frame size from `data-width`/
  `data-height`, not `getBoundingClientRect()`, or every line reads as past the frame.
- chrome-headless-shell needs no `--headless` flag; full Google Chrome needs `--headless=new` or `--dump-dom` opens a
  window. textcheck handles both.
- BiRefNet runs in its own Python (torch is not in the Reel Room venv). "no Python with torch + transformers" means the
  birefnet venv is missing (setup line in commands.md). A killed BiRefNet cutout resumes from `work/matte_alpha/`;
  changing `--quality` or re-assembling discards the parts. `auto` never picks birefnet: use it when hyperframes leaves
  a halo and there is time for a slow background job.
- Showcase review copies are concept demos of real people: they stay in the owner's own Room until the person agrees.
- Burned-in text ghosts: inpainting only the letter fill leaves the dark outline and shadow, so the words still read.
  Mask fill + outline + shadow as word blocks (repurpose.py does). Over hair or a face inpaint smears: use `ref` or
  cover it with the new style. Titles fade over several frames: the region window must include the fade but never
  cross a shot cut (a `ref` or `inpaint` window across a cut pastes the wrong picture).
- A blurred caption band is covered, not clean: it shows as a soft bar on every caption frame. New captions sit over
  it, or crop it out.


## Compiler lessons (2026-10-13, editorial-ui adapter + everyday beats)

- Cut-out backends on the EDIT reel (1847 frames): `cutout_cache.py` 182 s full reel (10 fps, ANE + CPU), only the
  needed frames in a pipeline run (~500 frames, 30 to 80 s); `hyperframes remove-background` 374 s (same u2net model,
  5 fps); BiRefNet-portrait ONNX on CPU 17 to 30 s per frame (hours; the torch BiRefNet venv is not installed). A
  guided-filter refine on the 320 px mask pulled the busy balcony into the edge, so the default is a plain cubic upsample.
- A library hero mounted inside editorial-ui's camera block (`<!--mvcam-->`) needs a z-index, else the plate video
  hides it in the render AND in snapshots while lint and DOM QA still see it (kitcards.HERO_Z).
- `plan_schema.invented` matched numbers as substrings ('0' passed because '100%' was said): fixed to whole numbers,
  same in `hero_schema._num_in`.
- Bake processes x x264 threads x OpenCV threads oversubscribe a shared machine (load 60+, 18 GB swap): cap at 3
  processes, 2 threads each; the per-cut bake cache matters more than more workers.
