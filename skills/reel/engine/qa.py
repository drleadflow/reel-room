#!/usr/bin/env python3
"""Reel Room QA gate. One command, one verdict.

  python qa.py <project> <render.mp4> [--json] [--no-joins] [--only a,b] [--no-cache] [--max-pause 0.35]

The checks run on the MASTER (loudness is only meaningful after mastering). Pass the raw render or the master:
  - if <stem>-master.mp4 exists and is newer than the render it is used ("using master ...")
  - otherwise qa runs deliver.py's master step itself first and says so
report.render is the file that was actually checked; report.source_render is what you passed in.

Writes <project>/qa/report.json  {pass, render, source_render, checks:[{name, pass, detail, skipped?}]}
and   <project>/qa/cut_check.jpg (before/after frames for every cut).
Exit code 0 = pass, 1 = fail, 2 = could not run. Prints "QA PASSED" or "QA FAILED: n checks (names)".

Checks (spec section 4 item 7)            --only names
  frames       render frame count == segments.json total, audio length matches video      frames
  loudness     integrated -14 LUFS +-1, true peak <= -1.0 dBTP (ffmpeg ebur128)          loudness
  joins        verdicts from work/joins.json (written by `splice.py <project> joins`): a join is ok, check or
               flagged; flagged fails, check only counts, a waived join passes with a note. If joins.json is
               missing, splice.py joins is run (slow: it transcribes every join).       joins
  safe_zone    layout_boxes.json vs the Reels safe zone                                    safe_zone
  captions     caption boxes never overlap the face box                                    captions
  legibility   white caption text on a bright background fails (background just outside the text has mean
               luma > 170) unless the box has style pill/scrim (a split-layout caption is a pill by spec)   legibility
  file_sizes   share <= 30 MB and review <= 15 MB when they exist                          file_sizes
  cut_shots    every cut shows the new shot on its first frame (frame diff + contact strip) cut_shots
  list_rules   numbers fixed, active row highlighted, list cleared (only with work/list.json) list_rules
  new_shot_captions  first 3 frames of every new shot: caption off the face and off other text   new_shot_captions
  motion v2 gates (qa_motion.py, targets per project.json motion.level; each check carries a plain-language label):
               motion_density, dead_frames, event_density, hdr_alpha, ease_lint, hero_scale, sfx_sync, behind_head,
               transition_budget, motion_strips (12 fps strips qa/motion_strip_*.jpg); metrics in qa/motion.json
  gap_audit    LAST: pauses, caption gaps, tiny clips, voiced seams on the final audio -> qa/gaps.json   gap_audit
               (details and options: qa_extra.py)

Caching: expensive measurements (ebur128, cut frame diffs and thumbnails, caption backgrounds) are cached per file
hash in ~/.reel-room/cache/qa/, so a repeat run on the same file is fast. --no-cache ignores the cache.

layout_boxes.json (written by the template) is read as {beats:[{t0,t1,layout,boxes:[...]}], speaker:[{t0,t1,face}]},
{boxes:[...]} or a plain list. A box is {kind|type|role, x,y,w,h (or x0,y0,x1,y1), t0/t1, text, style?, color?}.
Picture kinds (video, broll, image, panel, bg, speaker, face, seam) are not "readable" and are ignored by the
safe-zone test. Boxes of kind "face" and the "speaker" list give the face rectangle in final-frame pixels.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deliver  # master step + loudness measurement live there
import qa_extra as QX  # list rules, new-shot captions, gap audit
import qa_motion as QM  # motion v2 gates
import qa_more  # text collisions, caption phrasing, repeated frames from the cut

try:
    import cv2
except ImportError:  # keep the gate usable without OpenCV, just without the contact strip
    cv2 = None

FPS = 30
W, H = 1080, 1920
# Safe zone (spec section 5): nothing readable in the top 220 px or below y 1470, 35 px sides,
# right 100 px clear from y 1155.
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE, SAFE_RIGHT, SAFE_RIGHT_FROM_Y = 220, 1470, 35, 100, 1155
LUFS_TARGET, LUFS_TOL, TP_MAX = -14.0, 1.0, -1.0
SHARE_MAX, REVIEW_MAX = 30_000_000, 15_000_000
PICTURE_KINDS = {"video", "broll", "image", "panel", "bg", "background", "speaker", "face", "seam", "photo", "media"}
# Default caption placement from the spec, used only when layout_boxes.json is missing.
CAPTION_DEFAULT = {"split": (996, 70), "full": (1250, 90)}  # (centre y, height)
SPLIT_FACE_Y = 960 + 330  # split layout puts the face centre ~330 px under the seam
CAPTION_WIDTH_PER_CHAR = 32  # rough px per char at 54-68 px bold, for the fallback estimate only
LEGIBILITY_MAX_LUMA = 170   # white text needs a background darker than this (mean luma 0-255)
RING_PX = 10               # background is sampled in a ring this many px wide just outside the caption box
CHECKS = ["frames", "loudness", "joins", "safe_zone", "captions", "legibility", "file_sizes", "cut_shots",
          "list_rules", "new_shot_captions",
          "motion_density", "dead_frames", "event_density", "hdr_alpha", "ease_lint", "hero_scale", "sfx_sync",
          "behind_head", "transition_budget", "motion_strips",
          "text_collision", "caption_phrasing", "aroll_repeats",   # qa_more.py: textcheck, capcheck, aroll_fix
          "numbers_verified",                                       # qa_more.py: numgate (numcheck.py ledger)
          "gap_audit"]   # gap_audit stays last
CUT_MIN_DIFF = 6.0  # mean abs gray diff (0-255) that counts as "the picture changed"


# ---------------------------------------------------------------- cache
CACHE_DIR = os.path.join(os.environ.get("REEL_ROOM_HOME") or os.path.expanduser("~/.reel-room"), "cache", "qa")
USE_CACHE = True


def file_hash(path):
    """Fast content hash: size + 16 sampled 1 MB chunks (same idea as common.content_hash)."""
    h = hashlib.blake2b(digest_size=12)
    size = os.path.getsize(path)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        for i in range(16):
            f.seek(max(0, (size - 1_000_000) * i // 15))
            h.update(f.read(1_000_000))
    return h.hexdigest()


def text_hash(*parts):
    return hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).hexdigest()


def cache_get(key):
    if not USE_CACHE:
        return None
    try:
        with open(os.path.join(CACHE_DIR, key + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cache_put(key, data):
    if not USE_CACHE:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------------------------------------------------------------- helpers
def run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def fail(msg, code=2):
    print(f"qa: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def probe(path):
    r = run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
             "stream=codec_type,codec_name,width,height,r_frame_rate,duration,nb_read_packets",
             "-show_entries", "format=duration,size", "-of", "json", path])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "ffprobe failed")
    return json.loads(r.stdout)


def check(name, ok, detail, skipped=False):
    d = {"name": name, "pass": bool(ok), "detail": detail}
    if skipped:
        d["skipped"] = True
    return d


# ---------------------------------------------------------------- checks
def check_frames(info, segs):
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        return check("frames", False, "render has no video stream")
    got = int(v.get("nb_read_packets") or 0)
    want = max(s["frame"] + s["frames"] for s in segs) if segs else None
    notes, ok = [], True
    if want is None:
        notes.append("segments.json missing, frame count not compared")
    elif got != want:
        ok = False
        notes.append(f"render has {got} frames but segments.json expects {want}")
    else:
        notes.append(f"{got} frames = segments.json")
    if (int(v.get("width", 0)), int(v.get("height", 0))) != (W, H):
        ok = False
        notes.append(f"size is {v.get('width')}x{v.get('height')}, expected {W}x{H}")
    if v.get("r_frame_rate") != f"{FPS}/1":
        ok = False
        notes.append(f"frame rate {v.get('r_frame_rate')}, expected {FPS}/1")
    if not a:
        ok = False
        notes.append("render has no audio track")
    else:
        vd = got / FPS
        ad = float(a.get("duration") or info["format"].get("duration") or 0)
        if abs(ad - vd) > 0.15:
            ok = False
            notes.append(f"audio is {ad:.2f}s but video is {vd:.2f}s (drift)")
    return check("frames", ok, "; ".join(notes))


def check_loudness(path, fhash):
    key = "loud_" + fhash
    m = cache_get(key)
    cached = m is not None
    if m is None:
        got = deliver.measure_loudness(path)
        m = list(got) if got else None
        if m:
            cache_put(key, m)
    if not m:
        return check("loudness", False, "could not measure loudness (no audio?)")
    lufs, tp = m
    ok = abs(lufs - LUFS_TARGET) <= LUFS_TOL and tp <= TP_MAX
    detail = f"{lufs:.1f} LUFS (want {LUFS_TARGET:.0f} +-{LUFS_TOL:.0f}), true peak {tp:.1f} dBTP (want <= {TP_MAX})"
    if not ok:
        detail += ". Fix: run deliver.py, its master step normalises to -14 LUFS / -1.5 dBTP."
    return check("loudness", ok, detail + (" [cached]" if cached else ""))


def join_verdict(j):
    """ok | check | flagged, from the shared splice.py verdict (falls back to the older flagged/check booleans)."""
    v = j.get("verdict")
    if v in ("ok", "check", "flagged"):
        return v
    return "flagged" if j.get("flagged") else "check" if j.get("check") else "ok"


def check_joins(project, skip):
    here = os.path.dirname(os.path.abspath(__file__))
    splice = os.path.join(here, "splice.py")
    if skip:
        return check("joins", True, "skipped (--no-joins)", skipped=True)
    jpath = os.path.join(project, "work", "joins.json")
    data = load_json(jpath)
    ran = False
    if data is None:
        if not os.path.exists(splice):
            return check("joins", True, "skipped: work/joins.json missing and splice.py not found", skipped=True)
        try:
            r = run([sys.executable, splice, project, "joins", "--json"], timeout=1800)
        except subprocess.TimeoutExpired:
            return check("joins", False, "splice joins timed out")
        data, ran = load_json(jpath), True
        if data is None:
            return check("joins", False, f"splice joins failed: {(r.stderr or r.stdout)[-300:].strip()}")
    items = data.get("joins", [])
    verdicts = [join_verdict(j) for j in items]
    flagged = [j for j, v in zip(items, verdicts) if v == "flagged" and not j.get("waived")]
    waived = [j for j, v in zip(items, verdicts) if v == "flagged" and j.get("waived")]
    n_check = sum(1 for v in verdicts if v == "check")
    detail = f"{len(items)} joins, {len(flagged)} flagged, {n_check} to double-check"
    if waived:
        detail += f", {len(waived)} waived (accepted by you)"
    if flagged:
        detail += ": " + " | ".join(f"{j.get('a')}>{j.get('b')} @{j.get('t', 0):.2f}s " + "; ".join(j.get("notes") or [])
                                   for j in flagged[:5])
    detail += " [work/joins.json" + (", just run]" if ran else "]")
    return check("joins", not flagged, detail)


def _box_rect(b):
    if all(k in b for k in ("x", "y", "w", "h")):
        return b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    if all(k in b for k in ("x0", "y0", "x1", "y1")):
        return b["x0"], b["y0"], b["x1"], b["y1"]
    return None


def _box_time(b, default):
    t0 = b.get("t0", b.get("start", default[0]))
    t1 = b.get("t1", b.get("end", default[1]))
    return t0, t1


def load_boxes(project):
    """Flatten layout_boxes.json to [{kind, rect, t0, t1, text}] or None when absent."""
    raw = load_json(os.path.join(project, "layout_boxes.json"))
    if raw is None:
        return None
    flat = []

    def add(b, span, layout=None):
        r = _box_rect(b)
        if not r:
            return
        t0, t1 = _box_time(b, span)
        kind = str(b.get("kind") or b.get("type") or b.get("role") or "text").lower()
        flat.append({"kind": kind, "rect": r, "t0": t0, "t1": t1, "text": b.get("text", ""), "layout": layout,
                     "style": b.get("style"), "color": b.get("color"),
                     "readable": b.get("readable", kind not in PICTURE_KINDS)})

    if isinstance(raw, dict) and "beats" in raw:
        for beat in raw["beats"]:
            span = (beat.get("t0", beat.get("start", 0)), beat.get("t1", beat.get("end", 1e9)))
            for b in beat.get("boxes", []):
                add(b, span, beat.get("layout"))
    else:
        for b in (raw.get("boxes", []) if isinstance(raw, dict) else raw):
            add(b, (0, 1e9))
    return flat


def load_speaker_faces(project):
    """[(t0, t1, rect)] face rectangles in final-frame pixels from layout_boxes.json 'speaker' (measured by the template)."""
    raw = load_json(os.path.join(project, "layout_boxes.json"))
    out = []
    for sp in (raw.get("speaker", []) if isinstance(raw, dict) else []):
        f = sp.get("face")
        if f:
            out.append((sp["t0"], sp["t1"], (f["cx"] - f["w"] / 2, f["cy"] - f["h"] / 2, f["cx"] + f["w"] / 2, f["cy"] + f["h"] / 2)))
    return out


def check_safe_zone(boxes):
    if boxes is None:
        return check("safe_zone", True, "skipped: layout_boxes.json not found (the template writes it)", skipped=True)
    bad = []
    for b in boxes:
        if not b["readable"]:
            continue
        x0, y0, x1, y1 = b["rect"]
        why = []
        if y0 < SAFE_TOP:
            why.append(f"top {y0:.0f} < {SAFE_TOP}")
        if y1 > SAFE_BOTTOM:
            why.append(f"bottom {y1:.0f} > {SAFE_BOTTOM}")
        if x0 < SAFE_SIDE or x1 > W - SAFE_SIDE:
            why.append(f"sides {x0:.0f}..{x1:.0f} outside {SAFE_SIDE}..{W - SAFE_SIDE}")
        if x1 > W - SAFE_RIGHT and y1 > SAFE_RIGHT_FROM_Y:
            why.append(f"right 100 px column used below y {SAFE_RIGHT_FROM_Y}")
        if why:
            label = (b["text"] or b["kind"])[:24]
            bad.append(f"'{label}' @{b['t0']:.1f}s: " + ", ".join(why))
    n = sum(1 for b in boxes if b["readable"])
    if bad:
        return check("safe_zone", False, f"{len(bad)} of {n} readable boxes outside the safe zone: " + " | ".join(bad[:5]))
    return check("safe_zone", True, f"{n} readable boxes, all inside the safe zone")


def seg_at(segs, t):
    f = int(t * FPS)
    for s in segs:
        if s["frame"] <= f < s["frame"] + s["frames"]:
            return s
    return None


def face_rect(seg, facepos, boxes_face=None):
    """Face box in FINAL FRAME pixels. Split layout moves the face under the seam; full uses aroll pixels."""
    if boxes_face:
        return boxes_face
    fp = (facepos or {}).get(seg["id"])
    if not fp:
        return None
    cx, cy, h = fp["cx"], fp["cy"], fp["h"]
    if seg.get("mode") == "split":
        cy = SPLIT_FACE_Y
    half_w = 0.55 * h
    return (cx - half_w, cy - h / 2, cx + half_w, cy + h / 2)


def overlap(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > 0 and iy > 0 and ix * iy


def captions_from_words(words, segs):
    """Fallback caption boxes from spec defaults: 1-3 word groups, centred, at the mode's default y."""
    out, grp = [], []
    for w in words:
        grp.append(w)
        if len(grp) == 3 or re.search(r"[.?!]$", w["text"]):
            out.append(grp)
            grp = []
    if grp:
        out.append(grp)
    boxes = []
    for g in out:
        t0, t1 = g[0]["start"], g[-1]["end"]
        seg = seg_at(segs, (t0 + t1) / 2)
        if not seg:
            continue
        cy, hh = CAPTION_DEFAULT["split" if seg.get("mode") == "split" else "full"]
        txt = " ".join(w["text"] for w in g)
        wid = min(W - 70, len(txt) * CAPTION_WIDTH_PER_CHAR + 60)
        boxes.append({"kind": "caption", "rect": (W / 2 - wid / 2, cy - hh / 2, W / 2 + wid / 2, cy + hh / 2),
                      "t0": t0, "t1": t1, "text": txt, "readable": True})
    return boxes


def check_captions(project, boxes, segs, facepos):
    speaker = load_speaker_faces(project)
    if not facepos and not speaker:
        return check("captions", True, "skipped: work/facepos.json not found (run headpos.py)", skipped=True)
    estimated = False
    caps = [b for b in (boxes or []) if "caption" in b["kind"]]
    if not caps:
        words = load_json(os.path.join(project, "words.json"), [])
        if not words:
            return check("captions", True, "skipped: no caption boxes and no words.json", skipped=True)
        caps, estimated = captions_from_words(words, segs), True
    face_boxes = {}
    for b in (boxes or []):
        if b["kind"] == "face":
            face_boxes[(round(b["t0"], 2), round(b["t1"], 2))] = b["rect"]
    bad = []
    for c in caps:
        mid = (c["t0"] + c["t1"]) / 2
        seg = seg_at(segs, mid)
        if not seg:
            continue
        fb = next((r for (a, z), r in face_boxes.items() if a <= mid <= z), None) or \
            next((r for a, z, r in speaker if a <= mid < z), None)
        fr = face_rect(seg, facepos, fb)
        if fr and overlap(c["rect"], fr):
            bad.append(f"'{c['text'][:20]}' @{mid:.1f}s on {seg['id']}")
    src = "estimated from spec caption positions (layout_boxes.json absent)" if estimated else "layout_boxes.json"
    if bad:
        return check("captions", False, f"{len(bad)} of {len(caps)} captions overlap the face ({src}): " + " | ".join(bad[:5]))
    return check("captions", True, f"{len(caps)} captions clear of the face ({src})")


def declared_face(project, boxes, seg, t, facepos):
    """the planned face box at cut time t: layout_boxes face box > template speaker list > facepos.json"""
    fb = next((b["rect"] for b in (boxes or []) if b["kind"] == "face" and b["t0"] <= t < b["t1"]), None) or \
        next((r for a, z, r in load_speaker_faces(project) if a <= t < z), None)
    return face_rect(seg, facepos, fb)


def check_sizes(render):
    base = re.sub(r"-(master|share|review|silent)$", "", os.path.splitext(render)[0])
    notes, ok = [], True
    size = os.path.getsize(render)
    if size < 100_000:
        ok = False
    notes.append(f"render {size / 1e6:.1f} MB")
    for suffix, cap, label in (("-share.mp4", SHARE_MAX, "share"), ("-review.mp4", REVIEW_MAX, "review")):
        p = base + suffix
        if os.path.exists(p):
            s = os.path.getsize(p)
            good = s <= cap
            ok &= good
            notes.append(f"{label} {s / 1e6:.1f} MB (cap {cap / 1e6:.0f}){'' if good else ' TOO BIG'}")
        else:
            notes.append(f"{label} not made yet")
    return check("file_sizes", ok, ", ".join(notes))


# ---------------------------------------------------------------- cut check (frame level)
def read_frames(path, thumb_idx, full_idx, tw=135, th=240, fw=540, fh=960):
    """Decode the render once at fw x fh (streaming). Keep thumbnails (tw x th) for thumb_idx and full-size frames for full_idx."""
    want = set(thumb_idx) | set(full_idx)
    last = max(want) if want else -1
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"scale={fw}:{fh}:flags=area", "-pix_fmt", "bgr24",
           "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size, thumbs, fulls, i = fw * fh * 3, {}, {}, 0
    try:
        while i <= last:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            if i in want:
                fr = np.frombuffer(buf, np.uint8).reshape(fh, fw, 3)
                if i in thumb_idx:
                    thumbs[i] = cv2.resize(fr, (tw, th), interpolation=cv2.INTER_AREA)
                if i in full_idx:
                    fulls[i] = fr.copy()
            i += 1
    finally:
        p.kill()
        p.wait()
    return thumbs, fulls


def gray(f):
    return f.astype(np.float32).mean(axis=2)


def cut_need(segs):
    cuts = [s["frame"] for s in segs[1:]]
    return cuts, {n for c in cuts for n in (c - 2, c - 1, c, c + 1) if n >= 0}


def cut_cache_key(fhash, segs):
    return "cuts2_" + text_hash(fhash, [(s["frame"], s.get("mode")) for s in segs])


def panel_diff(a, b):
    """(top half, bottom half) mean abs gray difference between two thumbnails. In the split layout the top half is the
    graphics panel and the bottom half is the speaker; in the full layout both halves are the speaker."""
    d = np.abs(gray(a) - gray(b))
    mid = d.shape[0] // 2
    return float(d[:mid].mean()), float(d[mid:].mean())


def cut_check(segs, thumbs, fhash, out_jpg, moving_cuts=()):
    """moving_cuts: cut frames that carry a motion v2 transition (whip, zoom...): the picture keeps moving after the
    cut by design, so only the change ON the cut frame is judged there."""
    cuts, _ = cut_need(segs)
    if not cuts:
        return check("cut_shots", True, "single segment, no cuts to check", skipped=True)
    key = cut_cache_key(fhash, segs)
    cached = cache_get(key)
    npz = os.path.join(CACHE_DIR, key + ".npz")
    pairs = []
    if cached and os.path.exists(npz) and not thumbs:
        z = np.load(npz)
        rows_out = cached["rows"]
        pairs = [(r["name"], r["c"], z[f"a{i}"], z[f"b{i}"], r["d"]) for i, r in enumerate(rows_out)]
    else:
        rows_out = []
        for k, c in enumerate(cuts, 1):
            if c - 1 not in thumbs or c not in thumbs:
                continue
            fr = thumbs
            cut_t, cut_b = panel_diff(fr[c - 1], fr[c])
            aft_t, aft_b = panel_diff(fr[c], fr[c + 1]) if c + 1 in fr else (0.0, 0.0)
            rows_out.append({"name": f"{segs[k - 1]['id']}>{segs[k]['id']}", "c": c, "d": max(cut_t, cut_b),
                             "top": cut_t, "bot": cut_b, "aft_top": aft_t, "aft_bot": aft_b,
                             "layouts": [segs[k - 1].get("mode"), segs[k].get("mode")]})
            pairs.append((rows_out[-1]["name"], c, fr[c - 1], fr[c], rows_out[-1]["d"]))
        if USE_CACHE and pairs:
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                np.savez_compressed(npz, **{f"{t}{i}": p_[2 if t == "a" else 3] for i, p_ in enumerate(pairs) for t in "ab"})
                cache_put(key, {"rows": rows_out})
            except OSError:
                pass
    weak, late, top_only, spk_only = [], [], [], []
    for r in rows_out:
        at = f"{r['name']} @{r['c'] / FPS:.2f}s"
        full = r["layouts"] == ["full", "full"]
        top_name, bot_name = ("top of the frame", "bottom of the frame") if full else ("top panel", "speaker panel")
        top_ch, bot_ch = r["top"] >= CUT_MIN_DIFF, r["bot"] >= CUT_MIN_DIFF
        if not top_ch and not bot_ch:
            weak.append(f"{at}: neither the {top_name} ({r['top']:.1f}) nor the {bot_name} ({r['bot']:.1f}) changes, "
                        "a jump cut must land on a new shot, a layout change or a new insert")
            continue
        for name, ch, d, aft in ((top_name, top_ch, r["top"], r["aft_top"]), (bot_name, bot_ch, r["bot"], r["aft_bot"])):
            if ch and aft > d * 0.8 and aft > CUT_MIN_DIFF * 2 and r["c"] not in moving_cuts:
                late.append(f"{at}: the {name} is still changing a frame later ({aft:.1f} vs {d:.1f}), "
                            "it should switch on the cut frame itself")
        if top_ch and not bot_ch and not full:
            top_only.append(r["name"])
        elif bot_ch and not top_ch and not full:
            spk_only.append(r["name"])
    write_strip(pairs, out_jpg)
    n = len(rows_out)
    both = n - len(weak) - len(top_only) - len(spk_only)
    detail = (f"{n} cuts checked: {both} change both halves, {len(spk_only)} change the speaker panel only, "
              f"{len(top_only)} change the top panel only (new insert); contact strip qa/cut_check.jpg")
    if top_only:
        detail += f". Top panel only: {', '.join(top_only[:6])}"
    if weak:
        detail += f". {len(weak)} cuts show no change: " + " | ".join(weak[:4])
    if late:
        detail += f". {len(late)} half-frames not settled on the cut frame: " + " | ".join(late[:4])
    return check("cut_shots", not (weak or late), detail)


def write_strip(pairs, out_jpg):
    if cv2 is None or not pairs:
        return
    cols, tw, th = 5, 135, 240
    rows = (len(pairs) + cols - 1) // cols
    sheet = np.full((rows * (th + 22), cols * (2 * tw + 8), 3), 24, np.uint8)
    for i, (name, c, a, b, d) in enumerate(pairs):
        r, col = divmod(i, cols)
        x, y = col * (2 * tw + 8), r * (th + 22)
        sheet[y + 22:y + 22 + th, x:x + tw] = a
        sheet[y + 22:y + 22 + th, x + tw:x + 2 * tw] = b
        color = (80, 80, 255) if d < CUT_MIN_DIFF else (230, 230, 230)
        cv2.putText(sheet, f"{name} f{c} d{d:.0f}", (x + 2, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    cv2.imwrite(out_jpg, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ---------------------------------------------------------------- caption legibility
def rel_lum(rgb):
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def hex_rgb(v, default=(255, 255, 255)):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(v or ""))
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else default


def caption_boxes(boxes):
    return [b for b in (boxes or []) if "caption" in b["kind"] and (b["t1"] - b["t0"]) > 0]


def caption_frame_idx(boxes):
    return {min(int(((b["t0"] + b["t1"]) / 2) * FPS), 10**9) for b in caption_boxes(boxes)}


def legibility_key(fhash, boxes):
    return "legib_" + text_hash(fhash, json.dumps([(b["rect"], b["t0"], b["t1"], b["style"], b["layout"], b["color"]) for b in caption_boxes(boxes)]))


def check_legibility(boxes, fulls, fhash, fw=540):
    caps = caption_boxes(boxes)
    if boxes is None:
        return check("legibility", True, "skipped: layout_boxes.json not found (the template writes it)", skipped=True)
    if not caps:
        return check("legibility", True, "skipped: no caption boxes", skipped=True)
    key = legibility_key(fhash, boxes)
    rows = cache_get(key)
    cached = rows is not None
    if rows is None:
        if cv2 is None or not fulls:
            return check("legibility", False, "could not read frames for the legibility check")
        k = fw / W
        rows = []
        for b in caps:
            mid = (b["t0"] + b["t1"]) / 2
            fr = fulls.get(int(mid * FPS))
            if fr is None:
                continue
            x0, y0, x1, y1 = [v * k for v in b["rect"]]
            style = (b["style"] or ("pill" if b["layout"] == "split" else "")).lower()
            r = RING_PX * k
            ox0, oy0, ox1, oy1 = int(max(0, x0 - r)), int(max(0, y0 - r)), int(min(fr.shape[1], x1 + r)), int(min(fr.shape[0], y1 + r))
            ring = np.ones((oy1 - oy0, ox1 - ox0), bool)
            ring[int(y0 - oy0):int(y1 - oy0), int(x0 - ox0):int(x1 - ox0)] = False
            px = fr[oy0:oy1, ox0:ox1][ring]
            if len(px) < 30:
                continue
            rgb = px[:, ::-1].astype(np.float32)
            luma = float((0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]).mean())
            text_rgb = hex_rgb(b["color"])
            ratio = (max(rel_lum(text_rgb), rel_lum(rgb.mean(0))) + 0.05) / (min(rel_lum(text_rgb), rel_lum(rgb.mean(0))) + 0.05)
            rows.append({"t": round(mid, 2), "text": b["text"], "luma": round(luma, 1), "ratio": round(ratio, 2),
                         "style": style, "white": text_rgb == (255, 255, 255)})
        cache_put(key, rows)
    bad = [r for r in rows if r["style"] not in ("pill", "scrim") and
           ((r["white"] and r["luma"] > LEGIBILITY_MAX_LUMA) or (not r["white"] and r["ratio"] < 3.0))]
    pills = sum(1 for r in rows if r["style"] in ("pill", "scrim"))
    detail = f"{len(rows)} captions sampled ({pills} on a pill/scrim, exempt)"
    if bad:
        worst = sorted(bad, key=lambda r: -r["luma"])[:5]
        detail = (f"{len(bad)} captions hard to read against a bright background: " +
                  " | ".join(f"'{r['text'][:22]}' @{r['t']:.1f}s bg luma {r['luma']:.0f} contrast {r['ratio']}:1" for r in worst) +
                  ". Fix: give the caption a pill or scrim, or darken the shot behind it.")
    elif rows:
        full = [r for r in rows if r["style"] not in ("pill", "scrim")]
        if full:
            detail += f"; brightest unprotected background luma {max(r['luma'] for r in full):.0f} (limit {LEGIBILITY_MAX_LUMA})"
    return check("legibility", not bad, detail + (" [cached]" if cached else ""))


# ---------------------------------------------------------------- main
def resolve_master(render):
    """(path_to_check, note). Prefers an up-to-date <stem>-master.mp4, else builds it with deliver's master step."""
    base, ext = os.path.splitext(render)
    if base.endswith("-master"):
        return render, "render is already a master"
    master = re.sub(r"-(share|review|silent)$", "", base) + "-master.mp4"
    if master != base + "-master.mp4":      # pointed at a derived file (share/review/silent): never re-master from it
        return (master, f"using master {os.path.basename(master)}") if os.path.exists(master) else \
               (render, "checking the derived file itself (no master found)")
    if os.path.exists(master) and os.path.getmtime(master) >= os.path.getmtime(render):
        return master, f"using master {os.path.basename(master)}"
    print(f"qa: no up-to-date master next to {os.path.basename(render)}, running deliver's master step first "
          f"(loudness is only meaningful after mastering)", file=sys.stderr, flush=True)
    try:
        res = deliver.make_master(render, master)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        fail(f"could not make the master: {e}")
    return master, f"built master {os.path.basename(master)} ({res['lufs']} LUFS, {res['true_peak']} dBTP)"


def main():
    global USE_CACHE
    ap = argparse.ArgumentParser(description="Reel Room QA gate")
    ap.add_argument("project")
    ap.add_argument("render")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--no-joins", action="store_true", help="skip the splice joins check")
    ap.add_argument("--only", help="comma list of checks to run: " + ",".join(CHECKS))
    ap.add_argument("--no-cache", action="store_true", help="ignore and do not write the measurement cache")
    ap.add_argument("--max-pause", type=float, help="gap audit: longest allowed pause in seconds (default 0.35)")
    a = ap.parse_args()
    USE_CACHE = not a.no_cache
    project, source = os.path.abspath(a.project), os.path.abspath(a.render)
    if not os.path.isdir(project):
        fail(f"project folder not found: {project}")
    if not os.path.isfile(source):
        fail(f"render not found: {source}. Render first, then run qa again.")
    only = [c.strip() for c in a.only.split(",")] if a.only else CHECKS
    unknown = [c for c in only if c not in CHECKS]
    if unknown:
        fail(f"unknown check(s) {', '.join(unknown)}; choose from {', '.join(CHECKS)}")
    render, note = resolve_master(source)
    print(f"qa: {note}", file=sys.stderr, flush=True)
    try:
        info = probe(render)
    except (RuntimeError, ValueError) as e:
        fail(f"cannot read the render ({e}). Is ffmpeg installed? Run doctor.py.")
    segs = load_json(os.path.join(project, "segments.json"), [])
    facepos = load_json(os.path.join(project, "work", "facepos.json"))
    # segments.json written by assemble may not carry mode; merge it from edl.json
    edl = {e["id"]: e for e in load_json(os.path.join(project, "edl.json"), [])}
    for s in segs:
        s.setdefault("mode", edl.get(s["id"], {}).get("mode"))
    boxes = load_boxes(project)
    fhash = file_hash(render)

    # one decode pass for everything that needs pixels and is not cached yet
    thumbs, fulls = {}, {}
    need_cut = "cut_shots" in only and len(segs) > 1 and not (cache_get(cut_cache_key(fhash, segs)) and
                                                              os.path.exists(os.path.join(CACHE_DIR, cut_cache_key(fhash, segs) + ".npz")))
    need_leg = "legibility" in only and boxes is not None and caption_boxes(boxes) and cache_get(legibility_key(fhash, boxes)) is None
    need_new = "new_shot_captions" in only and len(segs) > 1 and bool(caption_boxes(boxes))
    lspec = QX.list_spec(project) if "list_rules" in only else None
    if cv2 is not None and (need_cut or need_leg or need_new or lspec):
        t_idx = cut_need(segs)[1] if need_cut else set()
        f_idx = (caption_frame_idx(boxes) if need_leg else set()) | (QX.new_shot_idx(segs, boxes) if need_new else set()) | \
            QX.list_frame_idx(lspec)
        thumbs, fulls = read_frames(render, t_idx, f_idx)

    results = {}
    if "frames" in only:
        results["frames"] = check_frames(info, segs)
    if "loudness" in only:
        results["loudness"] = check_loudness(render, fhash)
    if "joins" in only:
        results["joins"] = check_joins(project, a.no_joins)
    if "safe_zone" in only:
        results["safe_zone"] = check_safe_zone(boxes)
    if "captions" in only:
        results["captions"] = check_captions(project, boxes, segs, facepos)
    if "legibility" in only:
        results["legibility"] = check_legibility(boxes, fulls, fhash)
    if "file_sizes" in only:
        results["file_sizes"] = check_sizes(render)
    if "cut_shots" in only:
        try:
            mplan = QM.M.load_plan(project) or {}
            results["cut_shots"] = cut_check(segs, thumbs, fhash, os.path.join(project, "qa", "cut_check.jpg"),
                                             {t["frame"] for t in mplan.get("transitions", [])})
        except Exception as e:  # never let the strip crash the gate
            results["cut_shots"] = check("cut_shots", False, f"could not run the cut check: {e}")
    k = 540 / W   # read_frames decodes at 540 x 960
    if "list_rules" in only:
        results["list_rules"] = QX.check_list_rules(project, fulls, k)
    if "new_shot_captions" in only:
        results["new_shot_captions"] = QX.check_new_shot_captions(
            project, boxes, segs, lambda seg, t: declared_face(project, boxes, seg, t, facepos), fulls, k)
    mwant = [c for c in only if c in QM.NAMES]
    if mwant:   # motion v2 gates (qa_motion.py): plain-language label per check, targets from the project's motion level
        try:
            for c in QM.run(project, render, os.path.join(project, "qa"), only=mwant):
                results[c["name"]] = c
        except Exception as e:  # noqa: BLE001  never let a motion gate crash the gate as a whole
            for n in mwant:
                results[n] = check(n, False, f"could not run the motion gates: {e}")
    for c in qa_more.run(project, only):   # text collisions, caption phrasing, repeated frames (qa_more.py)
        results[c["name"]] = c
    if "gap_audit" in only:
        results["gap_audit"] = QX.check_gap_audit(project, render, segs, a.max_pause, boxes)
    checks = [results[c] for c in CHECKS if c in results]

    failing = [c["name"] for c in checks if not c["pass"]]
    report = {"pass": not failing, "render": render, "source_render": source, "checks": checks}
    if a.only:
        report["partial"] = only      # a partial run is not a full gate
    os.makedirs(os.path.join(project, "qa"), exist_ok=True)
    with open(os.path.join(project, "qa", "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        for c in checks:
            tag = "SKIP" if c.get("skipped") else ("PASS" if c["pass"] else "FAIL")
            print(f"{tag}  {c['name']:<11} {c['detail']}")
        print("QA PASSED" if not failing else f"QA FAILED: {len(failing)} checks ({', '.join(failing)})")
    sys.exit(0 if not failing else 1)


if __name__ == "__main__":
    main()
