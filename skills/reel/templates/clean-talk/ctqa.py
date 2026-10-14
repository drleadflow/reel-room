#!/usr/bin/env python3
"""ctqa.py <project> <demo.mp4> <out_qa_dir> [--times 1.2,3.4] [--n 16]

Clean Talk eyes-on sheets (on top of split/styleqa.py):
  ct_sheet.jpg     ~16 frames spread over the render (390 px wide = phone size), labelled with time + caption word
  ct_cuts.jpg      the first 3 frames of every cut (caption vs face on a new shot), 390 px wide
  ct_peaks.json    volumedetect max / mean volume of the demo (peaks should sit around -2 to -5 dB, never 0)
  ct_times.jpg     optional exact times (--times), full 540 px wide for close reading
"""
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw

FPS = 30


def grab(video, frames, w):
    h = round(w * 16 / 9)
    sel = "+".join(f"eq(n\\,{f})" for f in sorted(set(frames)))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"select='{sel}',scale={w}:{h}:flags=lanczos",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    ims = [Image.frombytes("RGB", (w, h), raw[i * w * h * 3:(i + 1) * w * h * 3]) for i in range(n)]
    return dict(zip(sorted(set(frames)), ims))


def sheet(ims, labels, out, cols):
    w, h = ims[0].size
    rows = -(-len(ims) // cols)
    sh = Image.new("RGB", (cols * w, rows * (h + 24)), (16, 16, 18))
    d = ImageDraw.Draw(sh)
    for i, (im, lb) in enumerate(zip(ims, labels)):
        x, y = (i % cols) * w, (i // cols) * (h + 24)
        sh.paste(im, (x, y + 24))
        d.text((x + 6, y + 5), lb[:60], fill=(235, 235, 235))
    sh.save(out, quality=90)


def word_at(words, t):
    cur = ""
    for w in words:
        if w["start"] <= t + 1e-3:
            cur = w["text"]
    return cur


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    project, demo, qa = map(os.path.abspath, args[:3])
    os.makedirs(qa, exist_ok=True)
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    segs = json.load(open(os.path.join(project, "segments.json")))
    words = json.load(open(os.path.join(project, "words.json")))
    total = segs[-1]["frame"] + segs[-1]["frames"]
    n = int(opt("--n", 16))
    picks = [round(i * (total - 1) / (n - 1)) for i in range(n)]
    ims = grab(demo, picks, 390)
    sheet([ims[f] for f in picks], [f"{f / FPS:.2f}s '{word_at(words, f / FPS)}'" for f in picks],
          os.path.join(qa, "ct_sheet.jpg"), 8)
    cut_frames = [s["frame"] + k for s in segs[1:] for k in range(3)]
    ims = grab(demo, cut_frames, 390)
    sheet([ims[f] for f in cut_frames], [f"{s['id']} +{k}" for s in segs[1:] for k in range(3)],
          os.path.join(qa, "ct_cuts.jpg"), 6)
    if opt("--times"):
        fr = [round(float(t) * FPS) for t in opt("--times").split(",")]
        ims = grab(demo, fr, 540)
        sheet([ims[f] for f in fr], [f"{f / FPS:.2f}s" for f in fr], os.path.join(qa, "ct_times.jpg"), min(6, len(fr)))
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", demo, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mx = float(re.search(r"max_volume:\s*(-?[\d.]+)", err).group(1))
    mean = float(re.search(r"mean_volume:\s*(-?[\d.]+)", err).group(1))
    rep = {"max_volume_db": mx, "mean_volume_db": mean, "ok": -6.0 <= mx <= -1.0}
    json.dump(rep, open(os.path.join(qa, "ct_peaks.json"), "w"), indent=1)
    print(json.dumps(rep))


if __name__ == "__main__":
    main(sys.argv[1:])
