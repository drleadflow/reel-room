# Third-party notices

Reel Room includes code adapted from the projects below. Each adapted file names its source in a header comment.

## reel-kit

- Source: https://github.com/justynberk/reel-kit (studied at commit 99fbb0f)
- Used in: `skills/reel/engine/motion/motion.py` (transition key tables for whip, zoom, push and drop; the
  out/in frame easing; `cover()` overscan) and `skills/reel/engine/motion/motion.js` (`RRM.cover()`).
  Adapted from `fx/camera-transitions/fx.js`.
- Licence: MIT

```
MIT License

Copyright (c) 2026 Justyn Berkovits

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```


## reel-kit (component kit)

- Source: https://github.com/justynberk/reel-kit (studied at commit 99fbb0f), Copyright (c) 2026 Justyn Berkovits
- Used in: `skills/reel/templates/kit/` (the typer's pill-to-bar clip, per-character typing and PROMPT/SENT/DONE label
  states, adapted from `fx/prompt-bar`; the comment field flow of `comment-cta` (keyword typed on the word, post, heart),
  adapted from `fx/comment-cta`). Header comments in `rrkit.py`, `comps_fx.py`, `kit_ui.js` and `kit_fx.js` name the
  sources. Everything else in the kit is Reel Room's own.
- Licence: MIT, full text in the reel-kit section above.

## reel-kit (hero library)

- Source: https://github.com/justynberk/reel-kit (studied at commit 99fbb0f), Copyright (c) 2026 Justyn Berkovits
- Used in: `skills/reel/templates/kit/heroes_type.py` (the letter stamp of `title-stamp` / `word-stamp`, the set-up line
  and strike of `word-stamp`, and the magazine-cover beat order: rules from two corners, masthead letter-drop,
  coverlines rising out of line masks, sticker slap; adapted from `fx/word-stamp` and `fx/magazine-cover`),
  `heroes_edit.py` (the nle-timeline open-from-a-line, lanes landing by beat, per-frame timecode and fold-to-a-line,
  adapted from `fx/nle-timeline`; the video-card centre unfold, play press and chapter skip with a filling scrubber,
  adapted from `fx/video-card`) and `heroes_frame.py` (grid-collapse geometry and beats: the centre tile starting as
  the full frame, the backdrop one frame late, sides then corners popping, the seeded tilt and gravity fall, adapted
  from `fx/grid-collapse`). Header comments in those files name the sources. palette-fan, cycle-chart,
  money-counter, evidence-hero, fire-timeline and reel-orbit are Reel Room's own (reel-orbit is a clean-room build of a
  generic idea; no code or text from an unlicensed source was used).
- Licence: MIT, full text in the reel-kit section above.

## BiRefNet (ZhengPeng7/BiRefNet_HR-matting)

- Source: https://github.com/ZhengPeng7/BiRefNet, Bilateral Reference Network for high-resolution dichotomous image
  segmentation and matting, by Peng Zheng (ZhengPeng7) et al.
- Used by: `skills/reel/engine/matte_birefnet.py` (`cutout.py --engine birefnet`, opt-in). Weights are downloaded from
  Hugging Face at first use (not bundled); the model code is loaded through transformers `trust_remote_code`. The
  inference wrapper is adapted from Reel Room's own matte experiments (a test reel inserts).
- Licence: MIT.

## Blur-fusion foreground colour estimation

- Marco Forte and Francois Pitie, "Approximate Fast Foreground Colour Estimation", IEEE ICIP 2021.
- The algorithm is reimplemented in numpy/OpenCV in `skills/reel/engine/matte_birefnet.py` (`estimate_fg`,
  `blur_fusion`); no code copied.

## GSAP (GreenSock Animation Platform)

- Version 3.14.2, downloaded at install time from jsDelivr into `~/.reel-room/cache/` and copied into each project.
  It is NOT stored in this repository.
- Licence: the GSAP "Standard No Charge" licence (https://gsap.com/standard-license), owned by Webflow. GSAP is free,
  including for commercial use, but the licence does not allow using it in a product that competes with Webflow's own
  visual web-building / animation tools. Reel Room renders videos and is not a website builder, but the owner should
  confirm this reading before any paid or public release.

## Fonts (SIL Open Font License 1.1)

Bundled under `skills/reel/templates/*/fonts/` with `OFL.txt`: Inter, Inter Tight, Caveat (split template), DM Sans,
Playfair Display, JetBrains Mono (editorial-ui). Brand fonts you choose in `reel setup` are fetched from Google Fonts at
render time (OFL or Apache-2.0, per family).

## Ideas, no code

- The `/video-edit` skill by tenfoldmarc informed some editing ideas (take picking, safe zones, motion density). No
  code, text or assets from it are included.

## Runtime tools (not vendored, installed by the installer)

- HyperFrames 0.8.34 (Apache-2.0), run through npx.
- faster-whisper (MIT) and the Whisper small.en / medium.en models (MIT, OpenAI), downloaded from Hugging Face.
- u2net_human_seg.onnx (U^2-Net, Apache-2.0; released through rembg, MIT), downloaded at install time.
- FFmpeg (LGPL/GPL, installed separately), OpenCV (Apache-2.0), NumPy (BSD), Pillow (MIT-CMU), ONNX Runtime (MIT).
