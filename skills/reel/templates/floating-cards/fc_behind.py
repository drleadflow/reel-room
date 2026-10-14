"""Floating Cards: the big word BEHIND the speaker's head, live in the composition (Motion v2).

The word is a normal HTML layer (letters rise out of a mask, letter by letter), and a short cut-out clip of the
speaker plays above it only inside the word's window. Both sit in #fcCam, which follows the engine camera (#mvCam)
key for key, so every settle, push and punch moves the word and the head together.

The cut-out clip is baked here, not read raw from assets/aroll_matte.webm:
  - it carries the SAME grade as the base plate (so the head does not change colour inside the window)
  - its matte is refined like stylekit/behind.py (temporal smoothing, clean-plate test, guided edges)
  - its colour is edge-decontaminated (F = (I - (1 - a) B) / a), so the old wall never rims the cap over the word
  - it is cropped to the word's band (smaller file, faster render) and encoded VP9 alpha, bt709, GOP 30 (hdr.py safe)
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
import behind as bh  # noqa: E402
import kit  # noqa: E402
from kit import FPS, esc  # noqa: E402

W, H = 1080, 1920
PAD_ROWS = 48          # rows above/below the word band the clip keeps (letters rise and the camera moves)
TAIL = 3               # coverage gate: the clip outlives its window by 3 frames


def window(proj, b, resolve):
    f0, _ = resolve(proj, b["at"])
    f1, _ = resolve(proj, b["until"], f0 / FPS + 0.1)
    return f0, f1


def band(b):
    y, size = int(b.get("y", 600)), int(b.get("size", 300))
    y0 = max(0, (y - PAD_ROWS) // 2 * 2)
    y1 = min(H, (y + size + PAD_ROWS + 1) // 2 * 2)
    return y0, y1


def _frames(src, f_lo, f_hi, alpha=False):
    """Frames f_lo..f_hi (inclusive) of src: RGB uint8, or the alpha plane of a VP9-alpha webm."""
    vf = f"select='between(n\\,{f_lo}\\,{f_hi})'"
    cmd = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha else []) + ["-i", src, "-vf",
           vf + (",alphaextract" if alpha else ""), "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt",
           "gray" if alpha else "rgb24", "-"]
    per = W * H * (1 if alpha else 3)
    out = []
    for buf in bh._reader(cmd, per):
        out.append(np.frombuffer(buf, np.uint8).reshape((H, W) if alpha else (H, W, 3)))
    return out


def bake_clip(proj, b, f0, f1, grade, plate_frames, log=print):
    """-> (rel path of the cut-out clip, y0, y1, frame of its first picture). Cached by content."""
    y0, y1 = band(b)
    fa, fb = max(0, f0 - 1), min(proj.frames - 1, f1 + TAIL)
    src, matte = proj.p("assets", "aroll.mp4"), proj.p("assets", proj.style.get("matte", "aroll_matte.webm"))
    key = hashlib.sha1(json.dumps([b.get("text"), fa, fb, y0, y1, grade, os.path.getsize(matte), 3],
                                  sort_keys=True).encode()).hexdigest()[:10]
    rel = f"assets/fc_cut_{key}.webm"
    if os.path.exists(proj.p(rel)):
        return rel, y0, y1, fa
    log(f"behind-head cut-out: frames {fa}-{fb}, rows {y0}-{y1}")
    imgs = _frames(src, fa, fb)
    mats = _frames(matte, max(0, fa - 1), fb + 1, alpha=True)
    mats = [m.astype(np.float32) for m in mats]
    off = fa - max(0, fa - 1)            # index of frame fa inside mats
    g = bh.grade_lut(**grade) if grade else None
    ry0, ry1 = max(0, int(b.get("y", 600)) - 40), min(H, int(b.get("y", 600)) + int(b.get("size", 300)) + 41)
    plate = None
    if plate_frames:
        pl, valid = bh.clean_plate(src, matte, plate_frames, (y0, y1), log)
        plate = (pl, valid, y0, y1)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{y1 - y0}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                            "-g", "30", "-crf", "16", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            "-metadata:s:v:0", "alpha_mode=1", proj.p(rel)], stdin=subprocess.PIPE)
    for i, img in enumerate(imgs):
        k = i + off
        cur = mats[min(k, len(mats) - 1)]
        prev, nxt = mats[max(0, k - 1)], mats[min(len(mats) - 1, k + 1)]
        roi = (max(ry0, plate[2]), min(ry1, plate[3])) if plate else (ry0, ry1)
        a = bh.refine(prev, cur, nxt, img=img, roi=roi, plate=plate)
        graded = g(img) if g else img
        I = graded[y0:y1].astype(np.float32) / 255.0
        ab = a[y0:y1]
        B = bh.background_estimate(I, ab)
        F = (I - (1 - ab)[..., None] * B) / np.maximum(ab, 0.04)[..., None]
        F = np.where((ab > 0.02)[..., None], np.clip(F, 0, 1), I)
        rgba = np.concatenate([F, ab[..., None]], -1)
        enc.stdin.write(np.ascontiguousarray(np.clip(rgba * 255 + 0.5, 0, 255).astype(np.uint8)).tobytes())
    enc.stdin.close()
    enc.wait()
    if enc.returncode or not os.path.exists(proj.p(rel)):
        raise SystemExit("behind-head cut-out encode failed (ffmpeg libvpx-vp9 with alpha)")
    for old in os.listdir(proj.p("assets")):     # keep only the clips this config uses
        if old.startswith("fc_cut_") and old not in {os.path.basename(rel)} and old not in proj._fc_keep:
            os.remove(proj.p("assets", old))
    proj._fc_keep.add(os.path.basename(rel))
    return rel, y0, y1, fa


def hidden_letters(proj, b, f0, f1, w_est):
    """Letters the head really hides: silhouette columns inside the word's band at the window's middle frame."""
    t = (f0 + f1) / 2 / FPS
    p = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.3f}", "-i",
                        proj.p("assets", proj.style.get("matte", "aroll_matte.webm")), "-frames:v", "1", "-vf",
                        "alphaextract,scale=540:960", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if len(p.stdout) != 540 * 960:
        return None, None
    a = np.frombuffer(p.stdout, np.uint8).reshape(960, 540)
    k = 2.0
    y, size = int(b.get("y", 600)), int(b.get("size", 300))
    rows = a[int(y / k):int((y + size) / k), :] > 128
    cols = rows.any(axis=0)
    x0, x1 = int((540 - w_est / 2) / k), int((540 + w_est / 2) / k)
    covered = float(cols[max(0, x0):max(0, x1)].sum() * k)
    ys = (a > 128).any(axis=1).nonzero()[0]
    head_top = float(ys[0] * k) if len(ys) else None
    return round(covered / max(1.0, w_est / max(1, len(b["text"]))), 2), head_top


def css(proj):
    acc = proj.colors["accent"]
    return f"""
#fcCam{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 960px}}
.fc-bh{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;white-space:nowrap;opacity:0;visibility:hidden;
  filter:drop-shadow(0 18px 40px rgba(29,18,20,.22)) drop-shadow(0 3px 8px rgba(29,18,20,.12))}}
.fc-bh .w{{display:inline-block;line-height:1;font-weight:900}}
.fc-bh .rc{{background:linear-gradient(180deg,color-mix(in srgb,{acc} 80%,#fff),{acc});-webkit-background-clip:text;
  background-clip:text;color:transparent}}
.fc-cut{{position:absolute;left:0;width:1080px}}
.fc-cut video{{position:absolute;left:0;top:0;width:1080px;height:100%;object-fit:fill}}
"""


def build(proj, tl, resolve, grade, plate_frames, log=print):
    """-> (html for #fcCam's inside, plan items for QA behind_head, cut-out windows)."""
    specs = [b for b in proj.style.get("behind", []) if b.get("live", True)]
    matte = proj.p("assets", proj.style.get("matte", "aroll_matte.webm"))
    if not specs:
        return "", [], []
    if not os.path.exists(matte):
        log("behind-head word needs assets/aroll_matte.webm (engine/cutout.py); skipped")
        return "", [], []
    proj._fc_keep = set()
    html, items, wins = [], [], []
    fam = proj.fonts["display"]
    for i, b in enumerate(specs):
        f0, f1 = window(proj, b, resolve)
        if f1 - f0 < 8:
            continue
        rel, y0, y1, fa = bake_clip(proj, b, f0, f1, grade, plate_frames, log)
        size, y = int(b.get("size", 300)), int(b.get("y", 600))
        wid = f"fcBh{i}"
        html.append(f'<div class="fc-bh" id="{wid}" style="top:{y}px"><span class="w" data-mfit="960" '
                    f'style="font:900 {size}px/1 \'{fam}\',sans-serif;letter-spacing:{b.get("ls", -0.045)}em">{esc(b["text"])}</span></div>')
        nfr = (f1 + TAIL) - fa + 1
        html.append(f'<div class="fc-cut" id="fcCut{i}" style="top:{y0}px;height:{y1 - y0}px"><video id="fcCutV{i}" src="{rel}" '
                    f'muted playsinline data-start="{fa / FPS:.5f}" data-media-start="0" data-duration="{nfr / FPS:.5f}" '
                    f'data-track-index="{70 + i}"></video></div>')
        t_in = (f0 - 2) / FPS              # letters start 2 frames early: the first one is half up on the word
        tl.set(f"#fcCut{i}", fa / FPS, {"autoAlpha": 1})
        tl.set(f"#fcCut{i}", (f1 + 1) / FPS, {"autoAlpha": 0})
        tl.set(f"#{wid}", t_in, {"autoAlpha": 1})
        tl.raw(f"RRM.enter('letters',tl,document.querySelector('#{wid} .w'),{t_in:.5f},"
               f"{{stagger:{b.get('stagger', 0.055)},dur:0.5,from:118,rot:8,blur:10}});")
        # exit: the letters sink back into the mask, 2x faster than they came
        n = len(b["text"])
        t_out = f1 / FPS - 0.2 - 0.02 * (n - 1)
        tl.raw(f"tl.to(document.querySelectorAll('#{wid} .rc'),{{yPercent:118,filter:'blur(6px)',duration:0.2,"
               f"ease:RRM.EASE.exit,stagger:0.02}},RRM.q({t_out:.5f}));")
        tl.set(f"#{wid}", f1 / FPS, {"autoAlpha": 0})
        tl.cue(f0 / FPS, b.get("sfx", "thump"))
        w_est = min(960, size * 0.64 * n)
        tl.event(f0 / FPS, "enter", f"behind-head word {b['text']}", region=[60, y, 960, size])
        hid, head_top = hidden_letters(proj, b, f0, f1, w_est)
        items.append({"text": b["text"], "t0": round(f0 / FPS, 3), "t1": round(f1 / FPS, 3), "chars": n,
                      **({"hidden_letters": hid} if hid is not None else {}),
                      "box": [round(540 - w_est / 2), y, round(w_est), size],
                      "head": [400, round(head_top or y + size * 0.4), 280, 400]})
        wins.append((round(fa / FPS, 3), round((f1 + TAIL) / FPS, 3)))
    return "\n".join(html), items, wins
