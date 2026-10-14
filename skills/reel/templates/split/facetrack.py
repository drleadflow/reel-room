#!/usr/bin/env python3
"""facetrack.py <project> [--step 3] [--video assets/aroll.mp4] [--out work/facetrack.json]

Per-frame face track of the assembled A-roll (aroll pixels, 1080x1920): the box every overlay must stay clear of.
Sampled every `step` frames (default 3) with the OpenCV Haar cascades (same models as engine/headpos.py), largest
face per frame. Missing samples are filled from the nearest detected sample inside the same segment and marked.

Output  {"step":3, "frames":N, "faces":{"<frame>":[cx,cy,h,detected(1|0)]}, "segments":{id:{head_top,chin,...}}}
  cx, cy  detector box centre;  h  detector box side (the box covers brow to mouth; chin ~ cy+0.8h, cap/hair top ~ cy-1.1h)

Used by: compose (overlay layer placement above the head), styleqa (face never covered, every 3rd frame).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD_UP = 1.1     # cap / hair top above the detector centre, in detector heights
CHIN_DOWN = 0.8   # chin below the detector centre


def _cv():
    try:
        import cv2  # noqa: F401
        return cv2
    except ImportError:
        venv = os.path.expanduser("~/.reel-room/venv/bin/python")
        if os.path.exists(venv) and os.path.realpath(sys.executable) != os.path.realpath(venv):
            os.execv(venv, [venv] + sys.argv)
        raise SystemExit("OpenCV missing: run engine/doctor.py")


def detect_track(video, step=3, scale=0.5):
    cv2 = _cv()
    casc = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
            ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out, idx = {}, 0
    while True:
        if not cap.grab():
            break
        if idx % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                g = cv2.cvtColor(cv2.resize(fr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                hit = None
                for c in casc:
                    f = c.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    if len(f):
                        x, y, w, h = max(f, key=lambda r: r[2] * r[3])
                        hit = ((x + w / 2) / scale, (y + h / 2) / scale, h / scale)
                        break
                out[idx] = hit
        idx += 1
    cap.release()
    return out, max(total, idx)


def build(project, step=3, video=None, out_rel="work/facetrack.json"):
    project = os.path.abspath(project)
    video = video or os.path.join(project, "assets", "aroll.mp4")
    segs = json.load(open(os.path.join(project, "segments.json")))
    raw, total = detect_track(video, step)
    faces, seg_info = {}, {}
    for s in segs:
        f0, f1 = s["frame"], s["frame"] + s["frames"]
        fr = [f for f in sorted(raw) if f0 <= f < f1]
        hits = [f for f in fr if raw[f]]
        # reject single-frame outliers (a detector jump of > 0.6 h from the segment median)
        if hits:
            med_cy = sorted(raw[f][1] for f in hits)[len(hits) // 2]
            med_h = sorted(raw[f][2] for f in hits)[len(hits) // 2]
            hits = [f for f in hits if abs(raw[f][1] - med_cy) < 0.6 * med_h and 0.7 * med_h < raw[f][2] < 1.35 * med_h]
        for f in fr:
            if f in hits:
                cx, cy, h = raw[f]
                faces[f] = [round(cx, 1), round(cy, 1), round(h, 1), 1]
            elif hits:
                near = min(hits, key=lambda k: abs(k - f))
                cx, cy, h = raw[near]
                faces[f] = [round(cx, 1), round(cy, 1), round(h, 1), 0]
        if hits:
            tops = [raw[f][1] - HEAD_UP * raw[f][2] for f in hits]
            chins = [raw[f][1] + CHIN_DOWN * raw[f][2] for f in hits]
            seg_info[s["id"]] = {"head_top": round(min(tops)), "chin": round(max(chins)), "n": len(hits),
                                 "of": len(fr), "cx": round(sorted(raw[f][0] for f in hits)[len(hits) // 2], 1)}
        else:
            seg_info[s["id"]] = {"n": 0, "of": len(fr)}
    data = {"step": step, "frames": total, "head_up": HEAD_UP, "chin_down": CHIN_DOWN,
            "faces": {str(k): v for k, v in sorted(faces.items())}, "segments": seg_info}
    path = os.path.join(project, out_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh)
    return data


def load(project):
    p = os.path.join(os.path.abspath(project), "work", "facetrack.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 3
    video = argv[argv.index("--video") + 1] if "--video" in argv else None
    out = argv[argv.index("--out") + 1] if "--out" in argv else "work/facetrack.json"
    d = build(args[0], step, video, out)
    det = sum(1 for v in d["faces"].values() if v[3])
    print(f"facetrack: {det}/{len(d['faces'])} sampled frames detected (every {step}), {d['frames']} frames")
    for sid, v in d["segments"].items():
        print(f"  {sid:6} n={v['n']}/{v['of']} head_top={v.get('head_top')} chin={v.get('chin')}")


if __name__ == "__main__":
    main(sys.argv[1:])
