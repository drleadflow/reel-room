"""Extra QA checks, wired into qa.py (they also run alone: qa.py P render --only gap_audit).

  list_rules         only when the style wrote work/list.json (else "not applicable"). Frame based:
                     numbers keep the same position and size on every reveal, the active row is highlighted, the list
                     region is clear after clear_at, rows are evenly spaced (from the spec boxes).
  new_shot_captions  first 3 frames of every new shot: the caption must not sit on the face (face found in the rendered
                     frame itself, declared face box as fallback) or on other on-screen text (layout_boxes.json).
                     A failing frame is saved as qa/new_shot_f<frame>.jpg with the boxes drawn.
  gap_audit          the final master audio (RMS envelope; the voice-only master when sound cues were mixed) + words.json: pauses longer than max_pause (default 0.35 s)
                     even under a caption, speech with no caption, tiny clips with no words, voice running through a cut
                     (clipped syllable). Report only, never fixes. Full list in qa/gaps.json.

work/list.json (written by a style that shows a list; full-frame pixels, cut-time seconds):
  {"items":[{"n":1, "t_in":13.6, "t_out":null, "box":[x,y,w,h] number glyph, "row":[x,y,w,h] optional}],
   "clear_at":35.0 (null = the list stays to the end), "scaffold":true (all numbers show from the first reveal),
   "settle":0.4 optional, "axis":"row" optional (a horizontal list: numbers share a row, slots evenly spaced in x)}.  t_in null = an item not revealed in this cut (scaffold placeholder).
project.json options:
  "gap_audit": {"max_pause":0.35, "min_clip":0.4, "tail_max":0.8}
  "gaps_ok": [{"t":12.4, "why":"deliberate pause before the punchline, listened"}]   waives the finding at that time
  "joins_ok" (from splice.py) also waives a voiced seam on that join.
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

FPS, W = 30, 1080
SETTLE = 0.4          # s after a reveal before the list is measured
NUM_SHIFT_MAX = 3.0   # px (full frame) a number may move between reveals
NUM_SIZE_TOL = 0.12   # relative size change allowed for a number glyph
INK_DIFF = 40         # a pixel is "ink" when it differs this much from the box's border colour
HIGHLIGHT_MIN = 6.0   # mean abs gray diff of the row, active vs not active
CLEAR_MIN = 12.0      # mean abs gray diff of a number box, last reveal vs after clear_at
ROW_GAP_TOL = 4       # px
NEW_SHOT_FRAMES = 3
FACE_PAD = 0.15       # Haar boxes run brow to mouth; grow 15 % up and down for forehead and chin
GAP_DEFAULTS = {"max_pause": 0.35, "min_clip": 0.4, "tail_max": 0.8, "caption_gap": 0.25}
WAIVE_WINDOW = 0.25


def _check(name, ok, detail, skipped=False):
    d = {"name": name, "pass": bool(ok), "detail": detail}
    if skipped:
        d["skipped"] = True
    return d


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def frame_at(t):
    return int(round(t * FPS))


# ================================================================ list rules
def list_spec(project):
    spec = _load(os.path.join(project, "work", "list.json"))
    if not isinstance(spec, dict) or not spec.get("items"):
        return None
    return spec


def _settle(spec):
    return float(spec.get("settle", SETTLE))


def list_frame_idx(spec):
    if not spec:
        return set()
    st, items, idx = _settle(spec), spec["items"], set()
    for it in items:
        if it.get("t_in") is None:
            continue
        idx.add(frame_at(it["t_in"] + st))
        idx.add(max(0, frame_at(it["t_in"]) - 2))
        if it.get("t_out") is not None:
            idx.add(frame_at(it["t_out"] + st))
    if spec.get("clear_at") is not None:
        idx.add(frame_at(spec["clear_at"] + st))
    return idx


def _crop(fr, box, k, pad=0):
    x, y, w, h = [v * k for v in box]
    x0, y0 = int(max(0, x - pad)), int(max(0, y - pad))
    x1, y1 = int(min(fr.shape[1], x + w + pad)), int(min(fr.shape[0], y + h + pad))
    return fr[y0:y1, x0:x1]


def glyph_geom(crop):
    """(cx, cy, w, h) of the ink inside a number box, in crop pixels, or None when the box is empty"""
    if crop.size == 0:
        return None
    px = crop.reshape(-1, 3).astype(np.int16)
    border = np.concatenate([crop[0], crop[-1], crop[:, 0], crop[:, -1]]).astype(np.int16)
    ref = np.median(border, axis=0)
    ink = (np.abs(crop.astype(np.int16) - ref).max(axis=2) > INK_DIFF)
    if ink.sum() < 6 or len(px) == 0:
        return None
    ys, xs = np.nonzero(ink)
    return (float(xs.mean()), float(ys.mean()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1))


def _gray_diff(a, b):
    if a is None or b is None or a.shape != b.shape or a.size == 0:
        return None
    return float(np.abs(a.astype(np.float32).mean(axis=2) - b.astype(np.float32).mean(axis=2)).mean())


def _numbers_steady(spec, fulls, k):
    """with "scaffold": true every number is on screen from the first reveal, so each is measured at every reveal"""
    st, items, bad, geoms = _settle(spec), spec["items"], [], {}
    scaffold = bool(spec.get("scaffold"))
    reveals = sorted(x["t_in"] for x in items if x.get("t_in") is not None)
    for i, it in enumerate(items):
        t_ref = reveals[0] if scaffold else it.get("t_in")
        if t_ref is None:
            continue
        ref = fulls.get(frame_at(t_ref + st))
        g0 = glyph_geom(_crop(ref, it["box"], k)) if ref is not None else None
        if g0 is None:
            bad.append(f"number {it.get('n', i + 1)} not visible at {mmss(t_ref + st)}")
            continue
        geoms[i] = g0
        for later in [x for x in items if x.get("t_in") is not None and x["t_in"] > t_ref]:
            fr = fulls.get(frame_at(later["t_in"] + st))
            if fr is None:          # reveal after the end of this render
                continue
            g = glyph_geom(_crop(fr, it["box"], k))
            if g is None:
                bad.append(f"number {it.get('n', i + 1)} gone at {mmss(later['t_in'] + st)}")
                continue
            shift = np.hypot(g[0] - g0[0], g[1] - g0[1]) / k
            size = max(abs(g[2] - g0[2]) / max(g0[2], 1), abs(g[3] - g0[3]) / max(g0[3], 1))
            if shift > NUM_SHIFT_MAX or size > NUM_SIZE_TOL:
                bad.append(f"number {it.get('n', i + 1)} moved {shift:.1f} px / resized {size:.0%} between "
                           f"{mmss(t_ref + st)} and {mmss(later['t_in'] + st)} (item {later.get('n')} reveal)")
    if len(geoms) > 1:
        hs = [g[3] for g in geoms.values()]
        row = spec.get("axis") == "row"   # a horizontal list: numbers share one baseline instead of one column
        cs = [items[i]["box"][1 if row else 0] * k + g[1 if row else 0] for i, g in geoms.items()]
        if (max(hs) - min(hs)) / max(min(hs), 1) > NUM_SIZE_TOL * 2:
            bad.append(f"numbers are not the same size ({min(hs) / k:.0f} to {max(hs) / k:.0f} px tall)")
        if (max(cs) - min(cs)) / k > NUM_SHIFT_MAX * 2:
            bad.append(f"numbers are not in one {'row' if row else 'column'} ({(max(cs) - min(cs)) / k:.0f} px apart)")
    return bad


def _active_highlight(spec, fulls, k):
    st, items, bad, measured = _settle(spec), spec["items"], [], 0
    for i, it in enumerate(items):
        if not it.get("row") or it.get("t_in") is None:
            continue
        end = it.get("t_out")
        if end is None and i + 1 < len(items):
            end = items[i + 1].get("t_in")
        if end is None:
            continue
        a, b = fulls.get(frame_at(it["t_in"] + st)), fulls.get(frame_at(end + st))
        d = _gray_diff(_crop(a, it["row"], k) if a is not None else None, _crop(b, it["row"], k) if b is not None else None)
        if d is None:
            continue
        measured += 1
        if d < HIGHLIGHT_MIN:
            bad.append(f"row {it.get('n', i + 1)} looks the same while active and after ({d:.1f}), the active item "
                       "should be highlighted")
    return bad, measured


def _cleared(spec, fulls, k):
    if spec.get("clear_at") is None:      # the list stays to the end of the reel: no next topic to clear for
        return []
    st, items = _settle(spec), spec["items"]
    after = fulls.get(frame_at(spec["clear_at"] + st))
    last = fulls.get(frame_at(max(x["t_in"] for x in items if x.get("t_in") is not None) + st))
    if after is None or last is None:
        return [f"could not read the frame after clear_at {mmss(spec['clear_at'])}"]
    still = [str(it.get("n", i + 1)) for i, it in enumerate(items)
             if (_gray_diff(_crop(last, it["box"], k), _crop(after, it["box"], k)) or 0) < CLEAR_MIN]
    return [f"numbers {', '.join(still)} still on screen after {mmss(spec['clear_at'])}"] if still else []


def _row_spacing(spec):
    ax = 0 if spec.get("axis") == "row" else 1      # horizontal list: gaps between columns along x
    rows = sorted((it["row"] for it in spec["items"] if it.get("row")), key=lambda r: r[ax])
    gaps = [b[ax] - (a[ax] + a[ax + 2]) for a, b in zip(rows, rows[1:])]
    if len(gaps) > 1 and max(gaps) - min(gaps) > ROW_GAP_TOL:
        return [f"row gaps are uneven ({min(gaps):.0f} to {max(gaps):.0f} px), space rows by their rendered height"]
    return []


def check_list_rules(project, fulls, k):
    spec = list_spec(project)
    if spec is None:
        return _check("list_rules", True, "not applicable: no work/list.json (only a style that shows a list writes it)",
                      skipped=True)
    if cv2 is None or not fulls:
        return _check("list_rules", False, "could not read frames for the list check")
    bad = _numbers_steady(spec, fulls, k)
    hl, measured = _active_highlight(spec, fulls, k)
    bad += hl + _cleared(spec, fulls, k) + _row_spacing(spec)
    cleared = f"cleared after {mmss(spec['clear_at'])}" if spec.get("clear_at") is not None else "stays to the end"
    detail = (f"{len(spec['items'])} items: numbers steady across reveals"
              f"{' (scaffold)' if spec.get('scaffold') else ''}, active highlight checked on {measured} rows, {cleared}")
    if bad:
        detail = f"{len(bad)} list problems: " + " | ".join(bad[:6])
    return _check("list_rules", not bad, detail)


# ================================================================ new shot captions
def _caps(boxes):
    return [b for b in (boxes or []) if "caption" in b["kind"] and b["t1"] > b["t0"]]


def shot_frames(seg, caps):
    """first 3 frames of the new shot, plus the first 3 frames of its first caption when that lands within 1 s
    (captions never span a cut, so the first caption of a shot usually starts a few frames after it)"""
    c, end = seg["frame"], seg["frame"] + seg["frames"]
    out = list(range(c, min(end, c + NEW_SHOT_FRAMES)))
    first = min((b["t0"] for b in caps if c / FPS <= b["t0"] < min(end, c + FPS) / FPS), default=None)
    if first is not None:
        f0 = int(np.ceil(first * FPS - 1e-6))
        out += [f for f in range(f0, min(end, f0 + NEW_SHOT_FRAMES)) if f not in out]
    return out


def new_shot_idx(segs, boxes):
    caps = _caps(boxes)
    return {f for s in segs[1:] for f in shot_frames(s, caps)}


def _cascades():
    out = []
    for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"):
        c = cv2.CascadeClassifier(cv2.data.haarcascades + n)
        if not c.empty():
            out.append(c)
    return out


def _cover(f, r):
    """fraction of candidate f (x, y, w, h) covered by rect r (x0, y0, x1, y1)"""
    ix = min(f[0] + f[2], r[2]) - max(f[0], r[0])
    iy = min(f[1] + f[3], r[3]) - max(f[1], r[1])
    return max(0.0, ix) * max(0.0, iy) / max(f[2] * f[3], 1.0)


def detect_face(cascades, fr, k, planned=None, graphics=()):
    """the speaker's face in a (scaled) frame -> rect in full-frame pixels, grown for forehead and chin.
    Only plausible detections count: 120 to 520 px tall and, when a planned face box exists, within 1.5 face heights of
    it and 0.5x to 2x its size (Haar also fires on posters, maps and photos). The one nearest the plan wins.
    A hit that sits on on-screen text (`graphics` rects, e.g. a chart's labels) is Haar firing on the graphic: dropped."""
    gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    cands = []
    for c in cascades:
        for f in c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(int(120 * k), int(120 * k)),
                                    maxSize=(int(520 * k), int(520 * k))):
            x, y, w, h = [float(v) / k for v in f]
            cands.append((x, y, w, h))
    cands = [f for f in cands if sum(_cover(f, g) for g in graphics) <= 0.08]
    if planned:
        px, py = (planned[0] + planned[2]) / 2, (planned[1] + planned[3]) / 2
        ph = max(planned[3] - planned[1], 1)
        near = lambda f: np.hypot(f[0] + f[2] / 2 - px, f[1] + f[3] / 2 - py)  # noqa: E731
        cands = [f for f in cands if near(f) < 1.5 * ph and 0.5 <= f[3] / ph <= 2.0]
        cands.sort(key=near)
    else:
        cands.sort(key=lambda f: -f[2] * f[3])
    if not cands:
        return None
    x, y, w, h = cands[0]
    return (x, y - FACE_PAD * h, x + w, y + h * (1 + FACE_PAD))


def _overlap(a, b, shrink=4):
    ix = min(a[2], b[2]) - max(a[0], b[0]) - shrink
    iy = min(a[3], b[3]) - max(a[1], b[1]) - shrink
    return ix > 0 and iy > 0


def _save_bad_frame(fr, k, rects, path):
    img = fr.copy()
    for r, col in rects:
        if r:
            cv2.rectangle(img, (int(r[0] * k), int(r[1] * k)), (int(r[2] * k), int(r[3] * k)), col, 2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def _shot_problems(f, t, caps, texts, face, fr, k, qa_dir):
    probs = []
    for c in caps:
        why = []
        if face and _overlap(c["rect"], face):
            why.append("on the face")
        hit = next((x for x in texts if _overlap(c["rect"], x["rect"])), None)
        if hit:
            why.append(f"on the text '{(hit['text'] or hit['kind'])[:18]}'")
        if why:
            path = os.path.join(qa_dir, f"new_shot_f{f}.jpg")
            _save_bad_frame(fr, k, [(face, (60, 60, 255)), (c["rect"], (0, 220, 255))] +
                            [(x["rect"], (255, 160, 0)) for x in texts], path)
            probs.append(f"frame {f} ({mmss(t)}): caption '{c['text'][:18]}' " + " and ".join(why))
    return probs


def check_new_shot_captions(project, boxes, segs, declared_face, fulls, k):
    """declared_face(seg, t) -> rect or None (qa.py supplies it from layout_boxes / facepos)"""
    if len(segs) < 2:
        return _check("new_shot_captions", True, "single shot, nothing to check", skipped=True)
    caps_all = _caps(boxes)
    if not caps_all:
        return _check("new_shot_captions", True, "skipped: no caption boxes in layout_boxes.json", skipped=True)
    if cv2 is None or not fulls:
        return _check("new_shot_captions", False, "could not read frames for the new-shot check")
    cascades, qa_dir = _cascades(), os.path.join(project, "qa")
    texts_all = [b for b in boxes if b["readable"] and "caption" not in b["kind"]]
    bad, measured, fallback = [], 0, 0
    for prev, seg in zip(segs, segs[1:]):
        for f in shot_frames(seg, caps_all):
            fr, t = fulls.get(f), f / FPS + 0.001
            if fr is None:
                continue
            caps = [c for c in caps_all if c["t0"] <= t < c["t1"]]
            if not caps:
                continue
            measured += 1
            planned = declared_face(seg, t)
            texts = [x for x in texts_all if x["t0"] <= t < x["t1"]]
            face = detect_face(cascades, fr, k, planned, [x["rect"] for x in texts]) if cascades else None
            if face is None:
                face, fallback = planned, fallback + 1
            bad += [f"cut {prev['id']}>{seg['id']} " + p for p in _shot_problems(f, t, caps, texts, face, fr, k, qa_dir)]
    detail = (f"{len(segs) - 1} cuts, {measured} new-shot frames with a caption (first 3 of each shot and of its first "
              "caption) checked against the face in the frame"
              + (f" ({fallback} used the planned face box, no face found)" if fallback else "") + " and other text")
    if bad:
        detail = f"{len(bad)} new-shot frames with a caption in the wrong place: " + " | ".join(bad[:5]) + \
                 ". See qa/new_shot_f<frame>.jpg"
    return _check("new_shot_captions", not bad, detail)


# ================================================================ gap audit
def gap_options(project, override=None):
    pj = _load(os.path.join(project, "project.json"), {}) or {}
    opts = {**GAP_DEFAULTS, **(pj.get("gap_audit") or {})}
    if override:
        opts["max_pause"] = override
    waive_t = [(float(w["t"]), w.get("why", "waived")) for w in (pj.get("gaps_ok") or []) if isinstance(w, dict) and "t" in w]
    waive_j = {(w.get("a"), w.get("b")) for w in (pj.get("joins_ok") or []) if isinstance(w, dict)}
    return opts, waive_t, waive_j


def master_env(render):
    import splice  # noqa: E402  (engine folder is on sys.path via qa.py)
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", render, "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", wav], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-200:] or "ffmpeg could not read the audio")
        return splice.load_env(wav), splice.HOP
    finally:
        os.unlink(wav)


def _pauses(env, hop, words, segs, dur, o):
    runs, out = env.runs(), []
    if not runs:
        return [{"kind": "no_speech", "t": 0.0, "detail": "no speech found in the master"}]
    cuts = [s["frame"] / FPS for s in segs[1:]]
    if runs[0][0] > o["max_pause"]:
        out.append({"kind": "pause", "t": 0.0, "t1": runs[0][0], "dur": round(runs[0][0], 2), "detail": "silence at the very start"})
    for (a0, a1), (b0, _) in zip(runs, runs[1:]):
        if b0 - a1 <= o["max_pause"]:
            continue
        under = [w["text"] for w in words if min(w["end"], b0) - max(w["start"], a1) > 0.15]
        cut = next((c for c in cuts if a1 <= c <= b0), None)
        where = ("across the cut at " + mmss(cut)) if cut is not None else "inside a shot"
        out.append({"kind": "pause", "t": round(a1, 2), "t1": round(b0, 2), "dur": round(b0 - a1, 2),
                    "detail": f"{b0 - a1:.2f} s pause {where}" + (f", hidden under the caption '{' '.join(under)[:24]}'" if under else "")})
    if dur - runs[-1][1] > o["tail_max"]:
        out.append({"kind": "pause", "t": round(runs[-1][1], 2), "t1": round(dur, 2), "dur": round(dur - runs[-1][1], 2),
                    "detail": f"{dur - runs[-1][1]:.2f} s of silence at the end"})
    return out


def _merge(spans, join=0.02):
    out = []
    for a, b, txt in sorted(spans):
        if out and a <= out[-1][1] + join:
            out[-1] = [out[-1][0], max(out[-1][1], b), txt if b >= out[-1][1] else out[-1][2]]
        else:
            out.append([a, b, txt])
    return out


def _caption_gaps(env, words, captions, o):
    """voice (merged voice runs) while no caption is on screen, for at least caption_gap seconds"""
    spans = _merge(captions or [(w["start"], w["end"], w["text"]) for w in words])
    out = []
    for (a0, a1, txt), (b0, _, _) in zip(spans, spans[1:]):
        if b0 - a1 <= o["caption_gap"]:
            continue
        talk = sum(max(0.0, min(r1, b0) - max(r0, a1)) for r0, r1 in env.runs())
        if talk >= o["caption_gap"]:
            out.append({"kind": "caption_gap", "t": round(a1, 2), "t1": round(b0, 2), "dur": round(talk, 2),
                        "detail": f"{talk:.2f} s of speech with no caption on screen after '{txt[-24:]}'"})
    return out


def _tiny_clips(words, segs, o):
    out = []
    for s in segs:
        t0, t1 = s["frame"] / FPS, (s["frame"] + s["frames"]) / FPS
        if t1 - t0 < o["min_clip"] and not any(t0 <= (w["start"] + w["end"]) / 2 < t1 for w in words):
            out.append({"kind": "tiny_clip", "t": round(t0, 2), "seg": s["id"],
                        "detail": f"{t1 - t0:.2f} s clip '{s['id']}' with no words"})
    return out


def _voiced_seams(env, hop, segs, waive_j):
    out = []
    for prev, s in zip(segs, segs[1:]):
        t = s["frame"] / FPS
        i = int(round(t / hop))
        db = float(env.db[max(0, i - 1):i + 1].max())   # the 10 ms on each side of the cut frame
        if db > env.speech:
            item = {"kind": "seam", "t": round(t, 2), "a": prev["id"], "b": s["id"],
                    "detail": f"voice runs through the cut {prev['id']}>{s['id']} ({db:.0f} dB), a syllable may be clipped"}
            if (prev["id"], s["id"]) in waive_j:
                item["waived"] = "joins_ok"
            out.append(item)
    return out


def gap_audit(project, render, segs, words, override=None, captions=None):
    o, waive_t, waive_j = gap_options(project, override)
    vo = render.replace("-master.mp4", "-voiceonly-master.mp4")
    if vo != render and os.path.exists(vo):   # sound cues: speech pauses are measured on the voice, not under the SFX
        render = vo
    env, hop = master_env(render)
    dur = len(env.db) * hop
    found = (_pauses(env, hop, words, segs, dur, o) + _caption_gaps(env, words, captions, o) +
             _tiny_clips(words, segs, o) + _voiced_seams(env, hop, segs, waive_j))
    for f in found:
        why = next((w for t, w in waive_t if abs(t - f["t"]) <= WAIVE_WINDOW), None)
        if why and "waived" not in f:
            f["waived"] = why
    found.sort(key=lambda f: f["t"])
    rep = {"render": render, "options": o, "voice_db": round(env.speech, 1), "floor_db": round(env.floor, 1), "findings": found}
    os.makedirs(os.path.join(project, "qa"), exist_ok=True)
    with open(os.path.join(project, "qa", "gaps.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    return rep


def check_gap_audit(project, render, segs, override=None, boxes=None):
    """boxes = qa.load_boxes() output; its caption boxes are what is really on screen (words.json is the fallback)"""
    words = _load(os.path.join(project, "words.json"), []) or []
    if not words:
        return _check("gap_audit", False, "words.json missing: run words.py build, the gap audit needs the captions")
    try:
        caps = [(b["t0"], b["t1"], b.get("text") or "") for b in _caps(boxes)] or None
        lb = _load(os.path.join(project, "layout_boxes.json"), {}) or {}
        if caps is not None:   # a caption hidden because the same words are on screen as type is still captioned
            caps += [(c["t0"], c["t1"], c["text"] + " (as type)") for c in lb.get("captions", []) if c.get("hidden")]
        rep = gap_audit(project, render, segs, words, override, caps)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
        return _check("gap_audit", False, f"could not run the gap audit: {e}")
    open_ = [f for f in rep["findings"] if not f.get("waived")]
    waived = len(rep["findings"]) - len(open_)
    kinds = {k: sum(1 for f in open_ if f["kind"] == k) for k in ("pause", "caption_gap", "tiny_clip", "seam", "no_speech")}
    head = (f"{kinds['pause']} pauses over {rep['options']['max_pause']} s, {kinds['caption_gap']} caption gaps, "
            f"{kinds['tiny_clip']} tiny clips, {kinds['seam']} voiced seams" + (f", {waived} waived" if waived else ""))
    if open_:
        head += ": " + " | ".join(f"{mmss(f['t'])} {f['detail']}" for f in open_[:6]) + ". Full list qa/gaps.json"
    else:
        head += ". Clean"
    return _check("gap_audit", not open_, head)
