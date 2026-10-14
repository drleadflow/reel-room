#!/usr/bin/env python3
"""styleqa.py <project> <demo.mp4> <out_dir>   -> <out_dir>/qa/report.json + contact sheets (exit 1 on fail)

Hard checks for style demos (beyond engine/qa.py):
  frames         demo frame count == segments; ceil(data_duration * 30) == frames
  safe_zone      every readable box inside: top 220, bottom 1470, sides 35, right 100 px clear below y 1155
  face_geometry  every 3rd frame: the face (per-frame track, mapped through the speaker placement) never overlaps a
                 caption / text / card / insert box on screen at that moment
  face_pixels    every 3rd frame: a face is detected in the FINAL render where the A-roll had one (an overlay covering
                 the face would kill the detection); misses near any box fail, isolated detector misses are listed
  captions       caption text == words.json word for word; no orphan chunks (pill mode); no em/en dashes on screen
  cuts           at every cut the picture changes ON the cut frame (diff N-1->N >> N->N+1), panels never blank
  audio          -14 LUFS +-0.5, true peak <= -1.5 dBTP, SFX >= 18 dB and bed >= 18 dB under the voice
  loop           loop.mp4 < 4 MB, 6 s, no audio track
Sheets: qa/cuts.jpg (N-1 | N | N+1 per cut), qa/events.jpg (each graphic just after it lands), qa/sheet.jpg (1 per 1.5 s),
qa/face_misses.jpg (frames where the render lost the face).
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FPS = 30
SAFE = {"top": 220, "bottom": 1470, "side": 35, "right_x": 980, "right_from": 1155}


def _cv():
    import cv2
    import numpy as np
    return cv2, np


def check(name, ok, detail):
    return {"name": name, "pass": bool(ok), "detail": detail}


def overlap(a, b, pad=0):
    ix = min(a[2], b[2]) + pad - max(a[0], b[0])
    iy = min(a[3], b[3]) + pad - max(a[1], b[1])
    return ix > 0 and iy > 0


def norm_words(s):
    return [re.sub(r"[^\w'0-9]+", "", w.lower().replace("’", "'")) for w in s.split() if re.sub(r"[^\w'0-9]+", "", w)]


def boxes_at(lb, t):
    out = []
    for bt in lb["beats"]:
        if not (bt["t0"] - 1e-3 <= t < bt["t1"] - 1e-3):
            continue
        for b in bt["boxes"]:
            if b["kind"] == "face":
                continue
            if b["t0"] - 1e-3 <= t < b["t1"] - 1e-3:
                out.append(b)
    return out


def placement_at(lb, t):
    for p in lb["speaker"]:
        if p["t0"] - 1e-6 <= t < p["t1"] - 1e-6:
            return p
    return lb["speaker"][-1]


def run(project, demo, out_dir):
    cv2, np = _cv()
    import layouts as lay
    import captions as caps_
    project = os.path.abspath(project)
    qa_dir = os.path.join(out_dir, "qa")
    os.makedirs(qa_dir, exist_ok=True)
    lb = json.load(open(os.path.join(project, "layout_boxes.json")))
    segs = json.load(open(os.path.join(project, "segments.json")))
    words = json.load(open(os.path.join(project, "words.json")))
    track = json.load(open(os.path.join(project, "work", "facetrack.json")))
    checks = []
    frames = lb["frames"]

    # ---- frames
    cap = cv2.VideoCapture(demo)
    n_demo = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    d = lb["data_duration"]
    ms = int(d.replace(".", ""))
    ceil_ok = -(-ms * FPS // 1000) == frames
    seg_total = segs[-1]["frame"] + segs[-1]["frames"]
    checks.append(check("frames", n_demo == frames == seg_total and ceil_ok,
                        f"demo {n_demo} frames, composition {frames}, segments {seg_total}, ceil({d}*30)={-(-ms * FPS // 1000)}"))

    # ---- safe zone
    bad = []
    nread = 0
    for bt in lb["beats"]:
        for b in bt["boxes"]:
            if not b.get("readable") or b["kind"] == "face":
                continue
            nread += 1
            x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
            why = []
            if y0 < SAFE["top"]:
                why.append(f"top {y0}")
            if y1 > SAFE["bottom"]:
                why.append(f"bottom {y1}")
            if x0 < SAFE["side"] or x1 > 1080 - SAFE["side"]:
                why.append(f"sides {x0}..{x1}")
            if x1 > SAFE["right_x"] and y1 > SAFE["right_from"]:
                why.append("right column below 1155")
            if why:
                bad.append(f"'{(b.get('text') or b['kind'])[:22]}' @{b['t0']:.1f}s {', '.join(why)}")
    bad = sorted(set(bad))
    checks.append(check("safe_zone", not bad, f"{nread} readable boxes; {len(bad)} outside: " + " | ".join(bad[:6])))

    # ---- face geometry, every 3rd frame
    hu, cd = track.get("head_up", 1.1), track.get("chin_down", 0.8)
    hits, tested = [], 0
    expected = {}
    import motionlayer  # engine/motion on sys.path
    mplan = motionlayer.M.load_plan(project) or {}
    tframes = motionlayer.M.transition_frames(mplan)   # whip/zoom frames are blurred on purpose: no face expected
    tcuts = {t["frame"] for t in mplan.get("transitions", [])}
    for k, v in track["faces"].items():
        f = int(k)
        t = (f + 0.5) / FPS
        if f in tframes:
            continue
        pl = placement_at(lb, t)
        if not pl.get("visible", True):
            continue
        skin, head = lay.face_box(pl, v[0], v[1], v[2], hu, cd)
        rect = (skin["x"], skin["y"], skin["x"] + skin["w"], skin["y"] + skin["h"])
        expected[f] = (rect, v[3])
        tested += 1
        for b in boxes_at(lb, t):
            if b["kind"] in ("insert",) and pl["layout"] == "split":
                continue  # split top-panel media live above the seam by construction
            br = (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])
            if overlap(rect, br):
                hits.append(f"f{f} {b['kind']} '{(b.get('text') or '')[:18]}'")
    checks.append(check("face_geometry", not hits,
                        f"{tested} frames checked (every {track['step']}), {len(hits)} overlaps " + " | ".join(hits[:6])))

    # ---- one pass over the render: face detection + frames for sheets
    casc = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
            ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
    cut_frames = [s["frame"] for s in segs[1:]]
    beat_frames = sorted({round(b["t0"] * FPS) for b in lb["inserts"] if b["t0"] > 0.01} |
                         {round(s["t0"] * FPS) for s in lb["speaker"] if s["t0"] > 0.01})
    switch_frames = sorted(set(cut_frames) | set(beat_frames))
    need = set()
    for f in switch_frames:
        need |= {f - 1, f, f + 1}
    for t in mplan.get("transitions", []):   # the frame after each transition lands (blank-panel check)
        need.add(min(frames - 1, t["span"][1] + 1))
    ev_frames = sorted({min(frames - 1, round((e["t"] + 0.45) * FPS)) for e in lb.get("events", [])})
    need |= set(ev_frames)
    sheet_frames = list(range(0, frames, 45))
    need |= set(sheet_frames)
    got, misses, det_n = {}, [], 0
    small = {}
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        want_face = idx in expected
        if idx in need or want_face:
            ok, fr = cap.retrieve()
            if not ok:
                break
            if idx in need:
                got[idx] = cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA)
                small[idx] = cv2.cvtColor(cv2.resize(fr, (270, 480), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
            if want_face and expected[idx][1]:
                g = cv2.cvtColor(cv2.resize(fr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                found = None
                for c in casc:
                    r = c.detectMultiScale(g, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                    if len(r):
                        found = [(x * 2, y * 2, w * 2, h * 2) for x, y, w, h in r]
                        break
                det_n += 1
                rect = expected[idx][0]
                cxe, cye = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
                good = found and any(abs(x + w / 2 - cxe) < 0.6 * (rect[2] - rect[0]) and abs(y + h / 2 - cye) < 0.8 * (rect[3] - rect[1])
                                     for x, y, w, h in found)
                if not good:
                    misses.append(idx)
                    got.setdefault(idx, cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA))
        idx += 1
    cap.release()
    near = []
    for f in misses:
        rect = expected[f][0]
        for b in boxes_at(lb, (f + 0.5) / FPS):
            br = (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])
            if overlap(rect, br, pad=40):
                near.append(f"f{f} near '{(b.get('text') or b['kind'])[:16]}'")
                break
    rate = len(misses) / max(det_n, 1)
    checks.append(check("face_pixels", not near and rate < 0.08,
                        f"face found in the render on {det_n - len(misses)}/{det_n} sampled frames where the A-roll had one; "
                        f"{len(misses)} detector misses ({rate:.1%}), {len(near)} next to an overlay " + " | ".join(near[:5])))

    # ---- captions
    caps = lb["captions"]
    cap_words = norm_words(" ".join(c["text"] for c in caps))
    src_words = norm_words(" ".join(w["text"] for w in words))
    diff = None
    if cap_words != src_words:
        i = next((k for k, (a, b) in enumerate(zip(cap_words, src_words)) if a != b), min(len(cap_words), len(src_words)))
        diff = f"first difference at word {i}: caption {cap_words[i:i + 4]} vs spoken {src_words[i:i + 4]}"
    orph = caps_.orphans(caps) if lb.get("caption_mode", "pill") != "word" else []
    html = open(os.path.join(project, "index.html")).read()
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    dashes = len(re.findall("[—–]", body)) + sum(1 for c in caps if re.search("[—–]", c["text"]))
    checks.append(check("captions", diff is None and not orph and dashes == 0,
                        f"{len(caps)} captions ({lb.get('caption_mode', 'pill')} mode; {sum(1 for c in caps if c.get('hidden'))} hidden while "
                        f"the same words are on screen as type), {len(cap_words)} words == words.json: "
                        f"{diff is None}{'; ' + diff if diff else ''}; orphans {orph or 'none'}; em/en dashes on screen {dashes}"))

    # ---- cuts: change lands ON the switch frame; panels not blank
    late, blank, rows = [], [], []

    def dif(a, b):
        return float(np.mean(np.abs(small[a] - small[b])))

    for f in switch_frames:
        if not all(k in small for k in (f - 1, f, f + 1)):
            continue
        d0, d1 = dif(f - 1, f), dif(f, f + 1)
        kind = "cut" if f in cut_frames else "switch"
        if d0 < 2.0 or (d1 > d0 * 0.6 and f not in tcuts):   # a transition keeps moving after its cut by design
            late.append(f"{kind} f{f} ({f / FPS:.2f}s): N-1->N {d0:.1f}, N->N+1 {d1:.1f}")
        pl = placement_at(lb, (f + 0.5) / FPS)
        if pl["layout"] in ("split", "card", "stage") and any(b["t0"] <= (f + .5) / FPS < b["t1"] for b in lb["inserts"]):
            fb = f
            if f in tcuts:   # an iris or zoom is still opening on the cut frame: judge the panel once it has landed
                fb = next((t["span"][1] + 1 for t in mplan.get("transitions", []) if t["frame"] == f), f)
                if fb not in small:
                    continue
            band = small[fb][int(220 / 4):int((960 if pl["layout"] == "split" else 940) / 4), :]
            if float(np.std(band)) < 6:
                blank.append(f"f{f}")
        rows.append((f, kind, d0, d1))
    checks.append(check("cuts", not late and not blank,
                        f"{len(rows)} switches checked ({len(cut_frames)} cuts); late/soft: {late[:5] or 'none'}; blank panels: {blank or 'none'}"))

    # ---- audio
    ap = os.path.join(qa_dir, "audio.json")
    if os.path.exists(ap):
        a = json.load(open(ap))
        dm = a.get("demo", {})
        sfx_ok = a.get("sfx_level", {}).get("under_voice_db", 99) >= 18
        bed_ok = (a.get("bed") or {}).get("under_voice_db", 99) >= 18
        ok = abs(dm.get("lufs", 0) + 14) <= 0.5 and dm.get("tp", 0) <= -1.5 and sfx_ok and bed_ok
        checks.append(check("audio", ok, f"demo {dm.get('lufs')} LUFS, TP {dm.get('tp')} dBTP; "
                                         f"SFX {len(a.get('sfx') or [])} events, loudest {a.get('sfx_level', {}).get('under_voice_db', '-')} dB under voice; "
                                         f"bed {(a.get('bed') or {}).get('under_voice_db', '-')} dB under"))
    # ---- loop
    lp = os.path.join(out_dir, "loop.mp4")
    if os.path.exists(lp):
        pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", lp],
                                       capture_output=True, text=True).stdout)
        kinds = [s["codec_type"] for s in pr.get("streams", [])]
        size = os.path.getsize(lp)
        dur = float(pr["format"]["duration"])
        checks.append(check("loop", size < 4_000_000 and "audio" not in kinds and abs(dur - 6) < 0.1,
                            f"{size / 1e6:.2f} MB, {dur:.2f}s, streams {kinds}"))

    # ---- sheets
    def tile(imgs, labels, cols, path, w=360, h=640):
        if not imgs:
            return
        rws = (len(imgs) + cols - 1) // cols
        canvas = np.zeros((rws * (h + 30), cols * w, 3), np.uint8)
        for i, (im, lab) in enumerate(zip(imgs, labels)):
            r, c = divmod(i, cols)
            canvas[r * (h + 30) + 30:r * (h + 30) + 30 + h, c * w:(c + 1) * w] = im
            cv2.putText(canvas, lab, (c * w + 6, r * (h + 30) + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(path, canvas, [cv2.IMWRITE_JPEG_QUALITY, 82])

    imgs, labs = [], []
    for f in switch_frames:
        for k in (f - 1, f, f + 1):
            if k in got:
                imgs.append(got[k])
                labs.append(f"{'CUT' if f in cut_frames else 'SW'} {k - f:+d} f{k} {k / FPS:.2f}s")
    tile(imgs, labs, 6, os.path.join(qa_dir, "cuts.jpg"))
    evl = sorted(lb.get("events", []), key=lambda e: e["t"])
    tile([got[f] for f in ev_frames if f in got], [f"{f / FPS:.2f}s" for f in ev_frames if f in got], 6,
         os.path.join(qa_dir, "events.jpg"))
    tile([got[f] for f in sheet_frames if f in got], [f"{f / FPS:.1f}s" for f in sheet_frames if f in got], 6,
         os.path.join(qa_dir, "sheet.jpg"))
    mm = [f for f in misses if f in got][:24]
    tile([got[f] for f in mm], [f"miss f{f} {f / FPS:.2f}s" for f in mm], 6, os.path.join(qa_dir, "face_misses.jpg"))

    # ---- motion v2 gates (engine/qa_motion.py) at the project's motion level
    if mplan:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "engine"))
        import qa_motion
        for c in qa_motion.run(project, demo, qa_dir):
            checks.append(c)
    ok = all(c["pass"] for c in checks)
    rep = {"pass": ok, "style": lb.get("style"), "demo": demo, "checks": checks,
           "events": evl, "warnings": lb.get("warnings", []),
           "switches": [{"frame": f, "kind": k, "d_prev": round(a, 2), "d_next": round(b, 2)} for f, k, a, b in rows]}
    with open(os.path.join(qa_dir, "report.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    for c in checks:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail'][:230]}")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        raise SystemExit(__doc__)
    sys.exit(0 if run(*a[:3]) else 1)
