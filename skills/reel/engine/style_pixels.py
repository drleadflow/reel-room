"""Reel Room style scan, pixel side: cheap offline numbers that support the AI read (style_ai.py).

Measured per video (first --max-seconds, sampled at 8 fps, no OCR):
  cuts_per_sec   scene changes (frame-to-frame gray difference well above the recent baseline)
  text           caption/title lines from an edge-and-shape heuristic: share of frames with text, % of frame
                 covered, line height, which of 5 vertical bands the text sits in
  palette        5 colours by k-means in Lab space, plus brightness, saturation, warmth
  framing        Haar face size and position, share of frames with a face, split_frac (hard horizontal seam
                 near the middle = top-graphic / bottom-speaker layout)
  pace           words per minute (faster-whisper when installed, else an estimate from voice energy)
"""
import json
import os
import subprocess
import tempfile

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

SAMPLE_FPS = 8
DEEP_EVERY = 4                      # heavier analyses (text, face, seam, palette) on every 4th sample = 2 fps
LONG_SIDE = 640
BANDS = ["top", "upper", "middle", "lower", "bottom"]


def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- video reading
def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration", "-of", "json", path])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-200:])
    d = json.loads(r.stdout)
    s = d["streams"][0]
    rot = 0
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = int(s.get("tags", {}).get("rotate", rot))
    w, h = int(s["width"]), int(s["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h, float(d["format"]["duration"])


def out_size(w, h):
    k = LONG_SIDE / max(w, h)
    return max(2, int(round(w * k / 2)) * 2), max(2, int(round(h * k / 2)) * 2)


def stream_frames(path, tw, th, seconds):
    """Yield BGR frames at SAMPLE_FPS, scaled to tw x th (ffmpeg applies the rotation itself)."""
    cmd = ["ffmpeg", "-v", "error", "-t", str(seconds), "-i", path, "-an", "-vf", f"fps={SAMPLE_FPS},scale={tw}:{th}",
           "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = tw * th * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(th, tw, 3)
    finally:
        p.kill()
        p.wait()


# ---------------------------------------------------------------- per-frame heuristics
_FACE = None


def face_cascade():
    global _FACE
    if _FACE is None:
        _FACE = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    return _FACE


def find_face(gray):
    c = face_cascade()
    if c.empty():
        return None
    faces = c.detectMultiScale(gray, 1.1, 5, minSize=(int(gray.shape[1] * 0.07),) * 2)
    return tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3])) if len(faces) else None


def text_lines(gray, face):
    """Caption/title lines: gradient -> horizontal close -> wide, short, edge-dense blobs outside the face."""
    h, w = gray.shape
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    bw = (grad > 60).astype(np.uint8) * 255
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, w // 18), 5)))
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 0.12 * w or ch < 0.02 * h or ch > 0.14 * h or cw / ch < 2.2 or cw > 0.98 * w:
            continue
        fill = float(bw[y:y + ch, x:x + cw].mean() / 255.0)
        if not 0.12 < fill < 0.75:
            continue
        if face:
            fx, fy, fw, fh = face
            ix = min(x + cw, fx + fw * 1.1) - max(x, fx - fw * 0.1)
            iy = min(y + ch, fy + fh * 1.1) - max(y, fy - fh * 0.1)
            if ix > 0 and iy > 0 and ix * iy > 0.5 * cw * ch:
                continue
        lines.append((x, y, cw, ch))
    return lines


def seam_ratio(gray):
    """Strength and row of a hard horizontal edge in the middle band (split layout)."""
    h, w = gray.shape
    g = gray.astype(np.float32)
    prof = np.abs(np.diff(g, axis=0)).mean(axis=1)
    lo, hi = int(h * 0.38), int(h * 0.62)
    band = prof[lo:hi]
    i = int(np.argmax(band))
    base = float(np.median(prof)) + 1.0
    return float(band[i] / base), (lo + i) / h


# ---------------------------------------------------------------- audio pace
_WHISPER = None


def whisper_model():
    """Load the small speech model once per scan (raises ImportError when faster-whisper is missing)."""
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        _WHISPER = WhisperModel(os.environ.get("REEL_SCAN_WHISPER", "base.en"), compute_type="int8")
    return _WHISPER

def pace_from_audio(path, seconds):
    """(words_per_min, source). faster-whisper when present, else a syllable-peak estimate from the energy."""
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        r = run(["ffmpeg", "-v", "error", "-y", "-t", str(seconds), "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav])
        if r.returncode != 0 or not os.path.exists(wav):
            return None, "no audio"
        try:
            model = whisper_model()
            segs, info = model.transcribe(wav, word_timestamps=False, condition_on_previous_text=False)
            words = sum(len(s.text.split()) for s in segs)
            dur = min(seconds, info.duration) or 1
            return round(words / dur * 60, 1), "faster-whisper"
        except Exception:
            pass
        import wave
        w = wave.open(wav)
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
        if len(a) < 16000:
            return None, "no audio"
        hop = 160
        n = len(a) // hop
        rms = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) / 32768 + 1e-9
        db = np.convolve(20 * np.log10(rms), np.ones(5) / 5, mode="same")
        floor = float(np.percentile(db, 10))
        active = db > floor + 12
        if active.mean() < 0.05:
            return None, "no speech found"
        env = np.convolve(rms, np.ones(7) / 7, mode="same")
        peaks = 0
        last = -100
        for i in range(2, n - 2):
            if active[i] and env[i] > env[i - 1] and env[i] >= env[i + 1] and env[i] > env[i - 2] and i - last >= 12:
                peaks += 1
                last = i
        speech_s = active.sum() * 0.01
        syl_per_s = peaks / speech_s
        return round(syl_per_s * 60 / 1.45 * float(active.mean() ** 0.5), 1), "estimated from voice energy"


# ---------------------------------------------------------------- one video
def analyze_video(path, max_seconds):
    w, h, dur = probe(path)
    tw, th = out_size(w, h)
    seconds = min(dur, max_seconds)
    prev, diffs, cut_times = None, [], []
    n = 0
    deep = {"face": [], "lines": [], "seam": [], "thumbs": [], "pixels": [], "luma": [], "sat": [], "warm": []}
    last_face = None
    rng = np.random.default_rng(7)
    for frame in stream_frames(path, tw, th, seconds):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (90, int(90 * th / tw)), interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev is not None:
            d = float(np.abs(small - prev).mean())
            base = float(np.median(diffs[-8:])) if len(diffs) >= 3 else 4.0
            if d > max(16.0, 4.0 * base):
                cut_times.append(n / SAMPLE_FPS)
                diffs.append(base)                      # do not let the cut itself raise the baseline
            else:
                diffs.append(d)
        prev = small
        if n % DEEP_EVERY == 0:
            face = find_face(gray)
            if face:
                last_face = face
            deep["face"].append(face)
            deep["lines"].append(text_lines(gray, face or last_face))
            deep["seam"].append(seam_ratio(gray))
            deep["thumbs"].append(cv2.resize(frame, (tw // 2, th // 2), interpolation=cv2.INTER_AREA))
            idx = rng.integers(0, tw * th, 1500)
            deep["pixels"].append(frame.reshape(-1, 3)[idx])
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            deep["luma"].append(float(gray.mean()))
            deep["sat"].append(float(hsv[..., 1].mean() / 255))
            deep["warm"].append(float((frame[..., 2].mean() - frame[..., 0].mean()) / 255))
        n += 1
    if n < 8:
        raise RuntimeError("video is too short or unreadable")
    secs = n / SAMPLE_FPS
    m = {"file": os.path.basename(path), "seconds": round(dur, 1), "analyzed_seconds": round(secs, 1),
         "size": f"{w}x{h}", "cuts": len(cut_times), "cuts_per_sec": round(len(cut_times) / secs, 3),
         "avg_shot_sec": round(secs / (len(cut_times) + 1), 2)}
    # text
    ls, k = deep["lines"], len(deep["lines"])
    with_text = [l for l in ls if l]
    areas = [sum(cw * ch for _, _, cw, ch in l) / (tw * th) * 100 for l in ls]
    all_lines = [x for l in ls for x in l]
    centers = [(y + ch / 2) / th for _, y, _, ch in all_lines]
    band_counts = [sum(1 for c in centers if int(min(4, c * 5)) == b) for b in range(5)]
    m["text"] = {"frames_with_text": round(len(with_text) / k, 3), "area_pct": round(float(np.mean(areas)), 2),
                 "line_height_pct": round(float(np.median([ch / th * 100 for *_, ch in all_lines])), 1) if all_lines else None,
                 "big_type_frac": round(sum(1 for l in ls if any(ch >= 0.06 * th for *_, ch in l)) / k, 3),
                 "caption_band": BANDS[int(np.argmax(band_counts))] if all_lines else None,
                 "band_share": {b: round(c / max(1, len(centers)), 2) for b, c in zip(BANDS, band_counts)}}
    # framing
    faces = [f for f in deep["face"] if f]
    fh = [f[3] / th for f in faces]
    cy = [(f[1] + f[3] / 2) / th for f in faces]
    med_h = float(np.median(fh)) if fh else None
    seams = deep["seam"]
    modal = float(np.median([s[1] for s in seams if s[0] > 5])) if any(s[0] > 5 for s in seams) else None
    split = [s for s in seams if s[0] > 5 and modal is not None and abs(s[1] - modal) < 0.03]
    m["framing"] = {"face_frac": round(len(faces) / k, 3), "face_height_pct": round(med_h * 100, 1) if fh else None,
                    "face_center_y": round(float(np.median(cy)), 2) if cy else None,
                    "type": ("faceless" if med_h is None or len(faces) / k < 0.15 else
                             "close-up" if med_h >= 0.22 else "medium" if med_h >= 0.10 else "wide"),
                    "split_frac": round(len(split) / k, 3), "seam_y": round(modal, 2) if modal else None}
    # colour
    px = np.concatenate(deep["pixels"]).astype(np.uint8).reshape(-1, 1, 3)
    lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    _, labels, centers_lab = cv2.kmeans(lab, 5, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3,
                                        cv2.KMEANS_PP_CENTERS)
    shares = np.bincount(labels.ravel(), minlength=5) / len(labels)
    cols = cv2.cvtColor(centers_lab.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR).reshape(-1, 3)
    order = np.argsort(-shares)
    m["palette"] = [{"hex": "#%02X%02X%02X" % (cols[i][2], cols[i][1], cols[i][0]), "share": round(float(shares[i]), 3)} for i in order]
    m["look"] = {"brightness": round(float(np.mean(deep["luma"])), 1), "saturation": round(float(np.mean(deep["sat"])), 3),
                 "warmth": round(float(np.mean(deep["warm"])), 3)}
    wpm, src = pace_from_audio(path, seconds)
    m["pace"] = {"words_per_min": wpm, "source": src}
    thumbs = deep["thumbs"]
    pick = [thumbs[int(i)] for i in np.linspace(0, len(thumbs) - 1, min(6, len(thumbs)))]
    return m, pick


def agg(per, getter):
    vals = [getter(p) for p in per]
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def merge_palettes(per):
    """Cluster every video's 5 colours (weighted by share) into 5 overall colours."""
    if len(per) == 1:
        return per[0]["palette"]
    cols, wts = [], []
    for p in per:
        for c in p["palette"]:
            h = c["hex"].lstrip("#")
            cols.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
            wts.append(c["share"] / len(per))
    rgb = np.array(cols, np.float32)
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    k = min(5, len(lab))
    _, labels, centers = cv2.kmeans(lab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 5,
                                    cv2.KMEANS_PP_CENTERS)
    share = np.zeros(k)
    for lbl, w in zip(labels.ravel(), wts):
        share[lbl] += w
    out = cv2.cvtColor(centers.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return [{"hex": "#%02X%02X%02X" % tuple(int(v) for v in out[i]), "share": round(float(share[i]), 3)}
            for i in np.argsort(-share)]


def contact_sheet(rows, out):
    """One row per video: up to 6 evenly spaced frames, with the file name above the row."""
    th = 240
    cells = []
    for name, frames in rows:
        r = [cv2.resize(f, (int(f.shape[1] * th / f.shape[0]), th)) for f in frames]
        strip = np.concatenate(r, axis=1)
        label = np.full((22, strip.shape[1], 3), 24, np.uint8)
        cv2.putText(label, name[:60], (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
        cells.append(np.concatenate([label, strip], axis=0))
    wmax = max(c.shape[1] for c in cells)
    cells = [np.pad(c, ((0, 0), (0, wmax - c.shape[1]), (0, 0)), constant_values=24) for c in cells]
    cv2.imwrite(out, np.concatenate(cells, axis=0), [cv2.IMWRITE_JPEG_QUALITY, 85])
