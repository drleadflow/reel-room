#!/usr/bin/env python3
"""Reel Room delivery: turn one finished render into every file the creator needs.

  python deliver.py <project> <render.mp4> [--cover PATH] [--out DIR] [--only a,b] [--json]

Files written next to the render (or --out), named after the render (<stem> = render name without .mp4):
  <stem>-master.mp4   two-pass loudnorm -14 LUFS / -1.5 dBTP, video stream copied (same logic as master_audio.py)
  <stem>-share.mp4    1080x1920 H.264 under 30 MB: bitrate computed from duration (min 1.5 Mbps), size verified
                      and re-encoded lower if it lands over
  <stem>-review.mp4   720x1280 H.264 under 15 MB, same method
  <stem>-silent.mp4   share video with no audio track (for trending sounds)
  <stem>-voice.m4a    voice only, from the master (from <stem>-voiceonly-master.mp4 when the render has sound cues)
  <stem>-voiceonly-master.mp4  only when render.py mixed sound cues: the same reel with the voice alone, mastered
  <stem>-cover.png    best frame (sharp, eyes region bright, eyes open) or --cover PATH
  <stem>.srt          captions from words.json, 1-3 words per cue, no em dashes
  covers/             `deliver.py <p> <render> covers [N]` (or --cover-options N): covers only, nothing else is touched.
                      N ranked clean-aroll frames (open eyes, sharpness, face size) + 2 hook-title versions (the hook
                      card from the render pasted on frames with open eyes and a quiet voice/closed mouth, inside the
                      hook segment first; `--at 12.3,18.0` forces the base frames), with covers/covers.json

stdout is always one JSON manifest [{label, path, size}, ...]; progress goes to stderr.
Sizes use decimal megabytes (30 MB = 30,000,000 bytes) so the cap holds on every platform.
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

FPS = 30
W, H = 1080, 1920
TARGET_I, TARGET_TP, TARGET_LRA = -14, -1.5, 9
MAX_KBPS = {"share": 8000, "review": 14000}
# Share keeps the spec minimum of 1.5 Mbps. The review copy is a throwaway for notes, so a 77 s reel must still fit
# 15 MB: it gets a lower floor and a lighter audio track.
MIN_KBPS = {"share": 2500, "review": 600}
FALLBACK_MIN_KBPS = 1500     # share at 900p may go lower than the 1080p floor
AUDIO_KBPS_BY = {"share": 128, "review": 64}
SHARE_MAX_MB = 19.0         # Room assets are capped at 20 MB per file; --share-max-mb changes this
CAPS = {"share": int(SHARE_MAX_MB * 1_000_000), "review": 15_000_000}
HEADROOM = 0.94          # aim below the cap: muxing overhead and rate-control wobble
SPLIT_FACE_Y = 960 + 330
EM_DASHES = "—–―"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def die(msg, fix=""):
    print(f"deliver: {msg}" + (f"\n  Fix: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(1)


def run(cmd, timeout=3600):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(cmd[0])} failed: {r.stderr.strip()[-600:]}")
    return r


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
             "-of", "json", path])
    d = json.loads(r.stdout)
    return float(d["format"]["duration"]), {s["codec_type"] for s in d["streams"]}


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- master
LUFS_TOL_MASTER, TP_CEIL = 0.5, -1.5


def measure_loudness(path):
    """(integrated LUFS, true peak dBTP) of the audio in `path`, or None if it cannot be measured."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    summ = txt[txt.rfind("Summary:"):] if "Summary:" in txt else ""
    mi = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summ)
    mp = re.search(r"True peak:\s*\n?\s*Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summ)
    if not mi or not mp:
        return None
    f = lambda v: float("-inf") if v == "-inf" else float(v)
    return f(mi.group(1)), f(mp.group(1))


def make_master(src, out):
    """Loudness master: -14 LUFS (+-0.5) and true peak <= -1.5 dBTP, video stream copied.

    Step 1 is the same two-pass loudnorm as engine/master_audio.py, rendered to a temporary 24-bit wav.
    Step 2 puts a true-peak limiter (oversampled to 192 kHz, alimiter) in front of the AAC encode, because loudnorm
    alone lands about 0.4 dB over its own peak target once AAC has encoded it. The result is measured and the
    limiter ceiling / gain trimmed up to 4 times until it is inside the target. Returns the measured numbers."""
    af1 = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn", "-af", af1, "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]+\}", r.stderr[r.stderr.rfind("[Parsed_loudnorm"):] if "[Parsed_loudnorm" in r.stderr else r.stderr, re.S)
    if not m:
        raise RuntimeError("could not measure loudness (does the render have an audio track?)")
    d = json.loads(m.group(0))
    if d["input_i"] in ("-inf", "inf"):
        raise RuntimeError("the render is silent, nothing to normalise")
    af2 = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={d['input_i']}:measured_TP={d['input_tp']}"
           f":measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']},aresample=48000")
    tmpdir = tempfile.mkdtemp(prefix="master_", dir=os.path.dirname(os.path.abspath(out)))
    wav = os.path.join(tmpdir, "normed.wav")
    try:
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-af", af2, "-c:a", "pcm_s24le", "-ar", "48000", wav])
        gain, ceil, got = 0.5, TP_CEIL - 0.4, None
        for attempt in range(1, 5):
            lim = max(0.0625, min(1.0, 10 ** (ceil / 20)))
            af = (f"volume={gain:.2f}dB,aresample=192000,alimiter=limit={lim:.4f}:attack=3:release=50:level=0,"
                  f"aresample=48000")
            run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                 "-af", af, "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out])
            got = measure_loudness(out)
            if not got:
                raise RuntimeError("could not measure the master")
            lufs, tp = got
            log(f"[master] try {attempt}: {lufs:.2f} LUFS, true peak {tp:.2f} dBTP")
            if abs(lufs - TARGET_I) <= LUFS_TOL_MASTER and tp <= TP_CEIL:
                return {"lufs": round(lufs, 2), "true_peak": round(tp, 2), "tries": attempt}
            if abs(lufs - TARGET_I) > 0.3:
                gain += TARGET_I - lufs
            if tp > TP_CEIL:
                ceil -= (tp - TP_CEIL) + 0.15
        raise RuntimeError(f"master landed at {got[0]:.1f} LUFS / {got[1]:.1f} dBTP, outside -14 +-0.5 / <= -1.5")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------- share / review
def encode_capped(src, out, width, height, cap, label):
    """H.264 at a bitrate derived from duration so the file lands under `cap` bytes; verify, retry lower.
    Share: video bitrate between 2.5 and 8 Mbps. If even the 2.5 Mbps floor would not fit, drop from 1080p to 900p
    (900x1600, floor 1.5 Mbps) and say so. Returns (size, note)."""
    dur, _ = probe(src)
    ak, top = AUDIO_KBPS_BY[label], MAX_KBPS[label]
    floor = MIN_KBPS[label]
    sizes = [(width, height, floor)]
    if label == "share":
        sizes.append((900, 1600, FALLBACK_MIN_KBPS))
    note = ""
    for si, (w, h, fl) in enumerate(sizes):
        budget = cap * HEADROOM * 8 / dur / 1000          # total kbps that fits
        vk = int(min(top, budget - ak))
        if vk < fl:
            if si + 1 < len(sizes):
                log(f"[{label}] {dur:.0f}s needs under {fl / 1000:.1f} Mbps to fit {cap / 1e6:.0f} MB at {w}x{h}: dropping to {sizes[si + 1][0]}x{sizes[si + 1][1]}")
                note = f"dropped to {sizes[si + 1][0]}x{sizes[si + 1][1]} to fit {cap / 1e6:.0f} MB"
                continue
            raise RuntimeError(f"{label}: {dur:.0f}s is too long for {cap / 1e6:.0f} MB at the {fl / 1000:.1f} Mbps minimum. "
                               f"Cut the reel shorter or raise the size limit.")
        for attempt in range(4):
            log(f"[{label}] encoding {w}x{h} at {vk} kbps (try {attempt + 1})")
            run(["ffmpeg", "-v", "error", "-y", "-i", src,
                 "-vf", f"scale={w}:{h}:flags=lanczos,format=yuv420p",
                 "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-b:v", f"{vk}k",
                 "-maxrate", f"{int(vk * 1.25)}k", "-bufsize", f"{vk * 2}k", "-r", str(FPS), "-g", "60",
                 "-c:a", "aac", "-b:a", f"{ak}k", "-ar", "48000", "-movflags", "+faststart", out])
            size = os.path.getsize(out)
            if size <= cap:
                return size, note
            scaled = int(vk * cap * HEADROOM / size * 0.97)
            log(f"[{label}] {size / 1e6:.1f} MB is over {cap / 1e6:.0f} MB, retrying at {scaled} kbps")
            if scaled < fl:
                break
            vk = scaled
        if si + 1 < len(sizes):
            note = f"dropped to {sizes[si + 1][0]}x{sizes[si + 1][1]} to fit {cap / 1e6:.0f} MB"
            continue
    raise RuntimeError(f"{label}: could not get under {cap / 1e6:.0f} MB without dropping below the minimum bitrate")


# ---------------------------------------------------------------- silent / voice
def make_silent(share, out):
    run(["ffmpeg", "-v", "error", "-y", "-i", share, "-an", "-c:v", "copy", "-movflags", "+faststart", out])


def make_voice(master, out):
    run(["ffmpeg", "-v", "error", "-y", "-i", master, "-vn", "-c:a", "aac", "-b:a", "192k", out])


# ---------------------------------------------------------------- cover
def _cascade(name):
    if cv2 is None:
        return None
    c = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, name))
    return c if not c.empty() else None


def candidate_times(dur, segs, n=48):
    """Evenly spread times, skipping 0.4 s near the start/end and 6 frames either side of a cut."""
    cuts = [s["frame"] for s in segs] if segs else []
    ts = []
    for t in np.linspace(0.5, max(0.6, dur - 0.5), n):
        f = int(t * FPS)
        if all(abs(f - c) > 6 for c in cuts):
            ts.append(float(t))
    return ts


def grab_frames(path, times):
    """Decode only the wanted frames (ffmpeg select) at 1080x1920 and return {time: BGR image}."""
    want = {int(t * FPS): t for t in times}
    order = sorted(want)
    expr = "+".join(f"eq(n\\,{n})" for n in order)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"select='{expr}'", "-vsync", "0",
                          "-frames:v", str(len(order)), "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    size, out = W * H * 3, {}
    try:
        for n in order:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            out[want[n]] = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
    finally:
        p.kill()
        p.wait()
    return out


def score_frame(img, face_cascade, eye_cascade, hint):
    """Higher is better: sharp face, bright (not blown) eye region, eyes detected open, face not tiny."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(cv2.resize(g, (540, 960)), 1.1, 5, minSize=(60, 60)) if face_cascade is not None else []
    if len(faces):
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face = (x * 2, y * 2, w * 2, h * 2)
    elif hint:
        cx, cy, h = hint
        face = (int(cx - 0.45 * h), int(cy - 0.5 * h), int(0.9 * h), int(h))
    else:
        return None
    x, y, w, h = face
    x, y = max(0, x), max(0, y)
    roi = g[y:y + h, x:x + w]
    if roi.size == 0:
        return None
    sharp = float(cv2.Laplacian(roi, cv2.CV_64F).var())
    eyes_roi = g[y + int(0.2 * h):y + int(0.5 * h), x:x + w]      # forehead-to-nose band holds the eyes
    eye_luma = float(eyes_roi.mean()) if eyes_roi.size else 0.0
    bright = 1.0 - min(1.0, abs(eye_luma - 150) / 110)            # best around 150, penalise dark or blown
    clipped = float((eyes_roi > 245).mean()) if eyes_roi.size else 0.0
    eyes_open = 0
    if eye_cascade is not None and eyes_roi.size:
        eyes_open = min(2, len(eye_cascade.detectMultiScale(eyes_roi, 1.1, 4, minSize=(max(12, w // 12),) * 2)))
    size_bonus = min(1.0, h / 260)
    # mouth openness proxy: share of very dark pixels in the mouth region (an open mouth shows a dark cavity)
    mouth = g[y + int(0.64 * h):y + int(0.92 * h), x + int(0.28 * w):x + int(0.72 * w)]
    mouth_open = float((mouth < 0.45 * max(1.0, float(np.median(roi)))).mean()) if mouth.size else 0.0
    return {"sharp": sharp, "bright": bright - clipped, "eyes": eyes_open, "size": size_bonus,
            "eye_luma": eye_luma, "face": (x, y, w, h), "mouth_open": mouth_open}


EYE_TERM = {0: 0.0, 1: 1.2, 2: 2.5}


def cover_score(s, sharp_ref):
    """Open eyes first (both eyes found = +2.5), then sharpness and face size, brightness only as a tie-break."""
    return float(EYE_TERM[min(2, s["eyes"])] + min(1.0, s["sharp"] / sharp_ref) * 2.0 + s["size"] * 1.2 + s["bright"] * 0.5)


HOOK_BONUS = 0.8       # the hook frame carries the headline, which a cover usually wants


def rank_candidates(video, segs, facepos, native, n=48, times=None):
    """Score evenly spaced frames of `video`. native=True: the video is the clean aroll, so facepos pixels apply
    as they are. native=False: the video is the finished render (split layout moves the face under the seam)."""
    dur, _ = probe(video)
    frames = grab_frames(video, times if times is not None else candidate_times(dur, segs, n))
    fc, ec = _cascade("haarcascade_frontalface_default.xml"), _cascade("haarcascade_eye.xml")
    scored = []
    for t, img in frames.items():
        scored.append((t, img, score_with_hint(img, t, segs, facepos, native, fc, ec)))
    ok = [x for x in scored if x[2]]
    sharp_ref = max(1.0, np.percentile([x[2]["sharp"] for x in ok], 90)) if ok else 1.0
    out = [{"t": t, "img": img, "stats": s, "score": cover_score(s, sharp_ref)} for t, img, s in ok]
    out.sort(key=lambda c: -c["score"])
    return out, sharp_ref


def score_with_hint(img, t, segs, facepos, native, fc, ec):
    seg = next((s for s in segs if s["frame"] <= int(t * FPS) < s["frame"] + s["frames"]), None) if segs else None
    fp = (facepos or {}).get(seg["id"]) if seg else None
    hint = None
    if fp:
        cy = fp["cy"] if native or seg.get("mode") != "split" else SPLIT_FACE_Y
        hint = (fp["cx"], cy, fp["h"])
    return score_frame(img, fc, ec, hint)


def describe(c):
    s = c["stats"]
    return f"frame at {c['t']:.1f}s (sharpness {s['sharp']:.0f}, eye brightness {s['eye_luma']:.0f}, eyes found {s['eyes']})"


def make_cover(render, aroll, out, segs, facepos, custom):
    """Default cover comes from the CLEAN aroll (no captions or graphics on it); the render is only the fallback."""
    if custom:
        if not os.path.isfile(custom):
            raise RuntimeError(f"cover file not found: {custom}")
        run(["ffmpeg", "-v", "error", "-y", "-i", custom, "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-frames:v", "1", out])
        return "custom cover"
    native = bool(aroll and os.path.isfile(aroll))
    video = aroll if native else render
    if cv2 is None:
        dur, _ = probe(video)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur * 0.35:.2f}", "-i", video, "-frames:v", "1", out])
        return "middle frame (OpenCV missing, install it for best-frame picking)"
    ranked, _ = rank_candidates(video, segs, facepos, native)
    if not ranked:
        frames = grab_frames(video, candidate_times(probe(video)[0], segs, 8))
        t, img = next(iter(frames.items()))
        cv2.imwrite(out, img)
        return f"frame at {t:.1f}s (no face found to rank)"
    cv2.imwrite(out, ranked[0]["img"])
    return ("clean aroll " if native else "render ") + describe(ranked[0])


def hook_card(project):
    """The hook card from layout_boxes.json: {rect (x0,y0,x1,y1), t (a time when it is fully on screen)} or None."""
    lb = load_json(os.path.join(project, "layout_boxes.json"), {})
    for beat in (lb.get("beats") if isinstance(lb, dict) else None) or []:
        for b in beat.get("boxes", []):
            if b.get("kind") in ("card", "hook") and "x" in b:
                t0, t1 = b.get("t0", beat.get("t0", 0)), b.get("t1", beat.get("t1", 1))
                return {"rect": (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]), "t": float(t0 + min(1.2, (t1 - t0) * 0.6)),
                        "span": (float(beat.get("t0", t0)), float(beat.get("t1", t1)))}
        break
    return None


def composite_card(base, card_img, rect, face, radius=34):
    """Paste the rendered hook card (rounded corners, soft shadow) onto a clean aroll frame. Moves it up if it would
    cover the face (never above y 240, the Reels safe zone is 220)."""
    x0, y0, x1, y1 = [int(v) for v in rect]
    w, h = x1 - x0, y1 - y0
    crop = card_img[y0:y1, x0:x1]
    if face and y0 + h + 24 > face[1]:
        y0 = max(240, face[1] - 24 - h)
    mask = np.zeros((h, w), np.uint8)
    cv2.rectangle(mask, (radius, 0), (w - radius, h), 255, -1)
    cv2.rectangle(mask, (0, radius), (w, h - radius), 255, -1)
    for cx, cy in ((radius, radius), (w - radius, radius), (radius, h - radius), (w - radius, h - radius)):
        cv2.circle(mask, (cx, cy), radius, 255, -1)
    out = base.copy()
    shadow = np.zeros(out.shape[:2], np.float32)
    shadow[y0 + 10:y0 + 10 + h, x0:x0 + w] = mask / 255.0
    shadow = cv2.GaussianBlur(shadow, (0, 0), 14) * 0.35
    out = (out.astype(np.float32) * (1 - shadow[..., None])).astype(np.uint8)
    roi = out[y0:y0 + h, x0:x0 + w]
    a = (mask.astype(np.float32) / 255.0)[..., None]
    out[y0:y0 + h, x0:x0 + w] = (crop * a + roi * (1 - a)).astype(np.uint8)
    return out


def quietness(video):
    """t -> 0..1: how quiet the voice is within +-0.1 s of t (1 = silent pause, 0 = loud speech). A closed or neutral
    mouth goes with a pause, so this is the proxy for 'mouth not mid-word'. Returns None if the audio cannot be read."""
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(wav):
            return None
        import wave
        w = wave.open(wav)
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    hop = 160
    n = len(a) // hop
    if n < 20:
        return None
    db = 20 * np.log10(np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) / 32768 + 1e-9)
    lo, hi = float(np.percentile(db, 10)), float(np.percentile(db, 90))

    def q(t):
        i = int(t * 100)
        win = db[max(0, i - 10):min(n, i + 11)]
        if not len(win):
            return 0.5
        return float(min(1.0, max(0.0, (hi - float(win.max())) / max(1.0, hi - lo))))
    return q


BASE_MIN_QUIET = 0.35


def base_score(c, sharp_ref, q):
    """Hook-title base frame: cover score + a quiet voice and a closed mouth (both keep the face neutral)."""
    st = c["stats"]
    quiet = q(c["t"]) if q else 0.5
    return cover_score(st, sharp_ref) + 2.2 * quiet + 0.8 * (1.0 - min(1.0, st.get("mouth_open", 0.0) * 6))


def pick_bases(count, video, segs, facepos, native, span, general, sharp_ref, q, at):
    """Frames to put the hook title on. at= forces times. Otherwise: open eyes + sharp + quiet voice/closed mouth,
    inside the hook segment first (only when a frame there is good enough), then anywhere. Returns candidates."""
    if at:
        ranked, _ = rank_candidates(video, segs, facepos, native, times=list(at))
        by_t = {round(c["t"], 3): c for c in ranked}
        missing = [t for t in at if round(t, 3) not in by_t]
        if missing:
            raise RuntimeError("no face found at " + ", ".join(f"{t}s" for t in missing) + " (pick another time)")
        return [dict(by_t[round(t, 3)], source="aroll", forced=True) for t in at]
    chosen = []
    ok_q = lambda c: (q(c["t"]) if q else 1.0) >= BASE_MIN_QUIET
    ok_sharp = lambda c: c["stats"]["sharp"] >= 0.8 * sharp_ref
    eyes2 = lambda c: c["stats"]["eyes"] >= 2
    tiers = []                                  # (candidates, minimum gap in s); tried in order until `count` are chosen
    if span:
        dur, _ = probe(video)
        times = [round(t, 2) for t in np.arange(span[0] + 0.2, min(span[1], dur) - 0.2, 0.1)]
        inside, _ = rank_candidates(video, segs, facepos, native, times=times) if times else ([], 1)
        tiers.append(([c for c in inside if eyes2(c) and ok_sharp(c) and ok_q(c)], 1.0))
    tiers += [([c for c in general if eyes2(c) and ok_sharp(c) and ok_q(c)], 3.0),    # best: anywhere, quiet voice
              ([c for c in general if eyes2(c) and ok_sharp(c)], 3.0),               # relax: any sharp open-eyed frame
              (list(general), 3.0)]
    for pool, gap in tiers:
        for c in sorted(pool, key=lambda c: -base_score(c, sharp_ref, q)):
            if all(abs(c["t"] - o["t"]) >= gap for o in chosen):
                chosen.append(dict(c, source="aroll"))
            if len(chosen) == count:
                return chosen
    return chosen


def make_cover_options(n, project, render, aroll, outdir, segs, facepos, at=None):
    """Ranked cover candidates: N clean aroll frames (>= 3 s apart) + 2 hook-title versions of the best two faces.
    A hook-title version is the clean aroll frame with the hook card cut from the finished render pasted on top
    (so it matches the reel exactly). Without a hook card in layout_boxes.json the render's own hook frame is used."""
    if cv2 is None:
        raise RuntimeError("OpenCV is needed to pick cover candidates (pip install opencv-python-headless)")
    os.makedirs(outdir, exist_ok=True)
    for old in glob.glob(os.path.join(outdir, "cover-*.png")):
        os.remove(old)
    native = bool(aroll and os.path.isfile(aroll))
    ranked, sharp_ref = rank_candidates(aroll if native else render, segs, facepos, native, n=max(90, n * 12))
    picks = []
    for c in ranked:
        if all(abs(c["t"] - p["t"]) >= 3.0 for p in picks):
            picks.append(dict(c, source="aroll" if native else "render"))
        if len(picks) == n:
            break
    dur, _ = probe(render)
    card = hook_card(project)
    if card and native and picks:
        frame = grab_frames(render, [min(card["t"], dur - 0.3)])
        if frame:
            card_img = next(iter(frame.values()))
            q = quietness(aroll)
            bases = pick_bases(len(at) if at else 2, aroll, segs, facepos, native, card.get("span"), ranked, sharp_ref, q, at)
            for base in bases:
                img = composite_card(base["img"], card_img, card["rect"], base["stats"].get("face"))
                why = "forced with --at" if base.get("forced") else f"voice quiet {q(base['t']):.2f}" if q else ""
                picks.append({"t": base["t"], "img": img, "stats": base["stats"], "score": base["score"] + HOOK_BONUS,
                              "source": "hook-title", "extra": why})
    elif not card or not native:
        th = min(1.0, dur - 0.3) if not card else min(card["t"], dur - 0.3)
        fc, ec = _cascade("haarcascade_frontalface_default.xml"), _cascade("haarcascade_eye.xml")
        hook = grab_frames(render, [th])
        if hook:
            img = next(iter(hook.values()))
            st = score_with_hint(img, th, segs, facepos, False, fc, ec) or {"sharp": 0, "bright": 0, "eyes": 0, "size": 0, "eye_luma": 0}
            picks.append({"t": th, "img": img, "stats": st, "score": cover_score(st, sharp_ref) + HOOK_BONUS, "source": "render-hook"})
    picks.sort(key=lambda c: -c["score"])
    items = []
    for i, c in enumerate(picks, 1):
        path = os.path.join(outdir, f"cover-{i:02d}-{c['source']}-{c['t']:.1f}s.png")
        cv2.imwrite(path, c["img"])
        items.append({"rank": i, "path": path, "t": round(c["t"], 2), "source": c["source"],
                      "score": round(c["score"], 3), "note": describe(c) + (f", {c['extra']}" if c.get("extra") else "")})
    with open(os.path.join(outdir, "covers.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return items


# ---------------------------------------------------------------- srt
def clean_caption(text):
    for ch in EM_DASHES:
        text = text.replace(ch, " ")
    return re.sub(r"\s+", " ", text).strip()


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_srt(words, max_words=3, gap_break=0.35):
    """Group words into 1-3 word cues. Break at sentence ends and long pauses. Cues never overlap."""
    ws = []
    for w in words:
        t = clean_caption(w.get("text", ""))
        if t:
            ws.append({"text": t, "start": float(w["start"]), "end": float(w.get("end", w["start"] + 0.2))})
    groups, cur = [], []
    for w in ws:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > gap_break):
            groups.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.?!]$", w["text"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    lines = []
    for i, g in enumerate(groups):
        start, end = g[0]["start"], max(g[-1]["end"], g[0]["start"] + 0.25)
        if i + 1 < len(groups):
            nxt = groups[i + 1][0]["start"]
            end = min(end + 0.12, nxt) if nxt - end < 0.3 else end
            end = min(end, nxt)
        lines.append(f"{i + 1}\n{srt_time(start)} --> {srt_time(end)}\n{' '.join(w['text'] for w in g)}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def write_downloads(project, outdir, stem, p):
    """room/downloads.json for the Room's Downloads tab: {items:[{label,desc,url,size,filename}]}.
    `url` is the LOCAL path: the caller swaps it for the asset url after uploading. Order: share, cover, captions
    (.srt copied to <stem>.srt.txt, a plain text file the Room can host), silent, voice-only (<stem>-audio.mp4,
    remuxed from the m4a with no re-encode). Only files that exist are listed."""
    srt, voice = p(".srt"), p("-voice.m4a")
    srt_txt, audio = p(".srt.txt"), p("-audio.mp4")
    if os.path.exists(srt):
        shutil.copyfile(srt, srt_txt)
    if os.path.exists(voice):
        run(["ffmpeg", "-v", "error", "-y", "-i", voice, "-vn", "-c:a", "copy", "-f", "mp4", "-movflags", "+faststart", audio])
    spec = [("Reel (share copy)", "The finished reel, 1080p, ready to post.", p("-share.mp4")),
            ("Cover", "The cover image for the reel.", p("-cover.png")),
            ("Captions", "Subtitle file with the words of the reel, for editors that import captions.", srt_txt),
            ("Reel with no sound", "The same reel with no audio, to add a trending sound inside Instagram.", p("-silent.mp4")),
            ("Voice only", "Just the voice, as an audio file.", audio)]
    out = os.path.join(project, "room", "downloads.json")
    old = {i["label"]: i for i in (load_json(out, {}) or {}).get("items", []) if os.path.exists(i.get("url", ""))}
    items = []
    for label, desc, path in spec:            # a partial run (e.g. --only share) keeps the other entries as they were
        if os.path.exists(path):
            items.append({"label": label, "desc": desc, "url": path, "size": os.path.getsize(path), "filename": os.path.basename(path)})
        elif label in old:
            items.append(old[label])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2)
    return items


def main():
    ap = argparse.ArgumentParser(description="Reel Room delivery")
    ap.add_argument("project")
    ap.add_argument("render")
    ap.add_argument("action", nargs="*", help="optional: 'covers [N]' = only write cover candidates (same as --cover-options N)")
    ap.add_argument("--cover", help="use this image as the cover instead of picking a frame")
    ap.add_argument("--cover-options", type=int, metavar="N",
                    help="also write N ranked cover candidates (clean aroll frames + the hook frame) to <out>/covers/ and covers.json")
    ap.add_argument("--share-max-mb", type=float, default=SHARE_MAX_MB,
                    help="byte budget for the share and silent copies in decimal MB (default 19: Room assets are capped at 20 MB)")
    ap.add_argument("--at", help="covers: comma list of times in seconds to use as the base frames of the hook-title covers, "
                                 "e.g. --at 12.3,18.0")
    ap.add_argument("--remaster", action="store_true", help="rebuild the master even if an up-to-date one exists")
    ap.add_argument("--out", help="output folder (default: next to the render)")
    ap.add_argument("--only", help="comma list of: master,share,review,silent,voice,cover,srt")
    ap.add_argument("--json", action="store_true", help="accepted for consistency; the manifest is always JSON")
    a = ap.parse_args()
    project, render = os.path.abspath(a.project), os.path.abspath(a.render)
    if not os.path.isfile(render):
        die(f"render not found: {render}", "render first, then run deliver again")
    outdir = os.path.abspath(a.out) if a.out else os.path.dirname(render)
    os.makedirs(outdir, exist_ok=True)
    stem = re.sub(r"\.[^.]+$", "", os.path.basename(render))
    for suf in ("-master", "-share", "-review", "-silent"):   # tolerate being pointed at a derived file
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    p = lambda suffix: os.path.join(outdir, stem + suffix)
    if a.action:
        if a.action[0] != "covers":
            die(f"unknown action '{a.action[0]}'", "use: deliver.py <project> <render> covers [N]")
        a.cover_options = int(a.action[1]) if len(a.action) > 1 else (a.cover_options or 6)
    CAPS["share"] = int(a.share_max_mb * 1_000_000)
    try:
        at = [round(float(x), 2) for x in a.at.split(",")] if a.at else None
    except ValueError:
        die(f"--at '{a.at}' is not a comma list of seconds", "example: --at 12.3,18.0")
    only = set(a.only.split(",")) if a.only else None
    if a.cover_options and only is None:
        only = {"cover-options"}                  # covers-only: never re-runs the delivery or touches the master
    want = lambda k: only is None or k in only

    segs = load_json(os.path.join(project, "segments.json"), [])
    edl = {e["id"]: e for e in load_json(os.path.join(project, "edl.json"), [])}
    for s in segs:
        s.setdefault("mode", edl.get(s["id"], {}).get("mode"))
    facepos = load_json(os.path.join(project, "work", "facepos.json"))
    words = load_json(os.path.join(project, "words.json"), [])

    manifest, errors = [], []

    def add(label, path, note=""):
        item = {"label": label, "path": path, "size": os.path.getsize(path)}
        if note:
            item["note"] = note
        manifest.append(item)
        log(f"[{label}] {path} ({item['size'] / 1e6:.2f} MB)")

    def step(label, fn):
        """Run one delivery step. Returns (ok, value); a failure is recorded, never raised."""
        try:
            return True, fn()
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
            errors.append(f"{label}: {e}")
            log(f"[{label}] FAILED: {e}")
            return False, None

    master_path = p("-master.mp4")
    aroll = os.path.join(project, "assets", "aroll.mp4")
    if any(want(k) for k in ("master", "share", "review", "silent", "voice")):
        fresh = os.path.exists(master_path) and os.path.getmtime(master_path) >= os.path.getmtime(render)
        if os.path.abspath(render) == master_path or (fresh and not a.remaster):
            log("[master] reusing the existing master")
            ok = True
        else:
            log("[master] loudnorm + true-peak limiter to -14 LUFS / <= -1.5 dBTP")
            ok, res = step("master", lambda: make_master(render, master_path))
            if ok:
                log(f"[master] {res['lufs']} LUFS, {res['true_peak']} dBTP after {res['tries']} tries")
        if ok and want("master"):
            add("master", master_path)
    src = master_path if os.path.exists(master_path) else render
    share_path = p("-share.mp4")
    if want("share") or want("silent"):
        ok, res = step("share", lambda: encode_capped(src, share_path, W, H, CAPS["share"], "share"))
        if ok and want("share"):
            add("share", share_path, res[1])
        if ok and want("silent"):
            ok2, _ = step("silent", lambda: make_silent(share_path, p("-silent.mp4")))
            if ok2:
                add("silent", p("-silent.mp4"))
    if want("review"):
        ok, _res = step("review", lambda: encode_capped(src, p("-review.mp4"), 720, 1280, CAPS["review"], "review"))
        if ok:
            add("review", p("-review.mp4"))
    # sound cues (render.py + soundcues.py) leave the plain voice render next to the mixed one: master it too, it is the
    # voice-only reel and the source of the voice-only audio (the SFX never leak into "Voice only")
    vo_render = os.path.join(os.path.dirname(render), stem + "-voiceonly.mp4")
    vsrc = src
    if os.path.exists(vo_render) and any(want(k) for k in ("master", "voice")):
        vo_master = p("-voiceonly-master.mp4")
        if os.path.exists(vo_master) and os.path.getmtime(vo_master) >= os.path.getmtime(vo_render) and not a.remaster:
            ok = True
        else:
            ok, _ = step("voiceonly-master", lambda: make_master(vo_render, vo_master))
        if ok:
            add("voiceonly-master", vo_master)
            vsrc = vo_master
    if want("voice"):
        ok, _ = step("voice", lambda: make_voice(vsrc, p("-voice.m4a")))
        if ok:
            add("voice", p("-voice.m4a"))
    if want("cover"):
        ok, note = step("cover", lambda: make_cover(render, aroll, p("-cover.png"), segs, facepos, a.cover))
        if ok:
            add("cover", p("-cover.png"), note)
    if a.cover_options and ("cover-options" in only or "cover" in only):
        cdir = os.path.join(outdir, "covers")
        ok, items = step("cover-options", lambda: make_cover_options(a.cover_options, project, render, aroll, cdir, segs, facepos, at))
        if ok:
            for it in items:
                add(f"cover-option-{it['rank']}", it["path"], f"{it['source']} score {it['score']}: {it['note']}")
            add("cover-options-list", os.path.join(cdir, "covers.json"))
    if want("srt"):
        if not words:
            errors.append("srt: words.json not found or empty")
        else:
            with open(p(".srt"), "w", encoding="utf-8") as f:
                f.write(build_srt(words))
            add("srt", p(".srt"))

    if any(want(k) for k in ("share", "cover", "srt", "silent", "voice")):
        try:
            dl = write_downloads(project, outdir, stem, p)
            log(f"[downloads] {len(dl)} items -> {os.path.join(project, 'room', 'downloads.json')}")
        except (OSError, subprocess.SubprocessError, RuntimeError) as e:
            errors.append(f"downloads: {e}")
    for e in errors:
        print(f"deliver: {e}", file=sys.stderr)
    print(json.dumps(manifest, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
