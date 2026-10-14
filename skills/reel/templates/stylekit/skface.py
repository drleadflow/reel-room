#!/usr/bin/env python3
"""skface.py <video> <out.json> [--step 3]
Face box on every `step`-th frame (OpenCV Haar, frontal + profile fallback), gaps filled by interpolation.
Output: {"step":3,"fps":30,"frames":N,"boxes":{"<frame>":[x,y,w,h], ...}} in video pixels. Used by qa.py checks
("nothing covers the face") and by templates that place cards around the head."""
import json
import sys

import cv2
import numpy as np


ROI = (0.25, 0.68)   # faces live in this vertical band of a 9:16 talking head (rejects shirt prints, posters)


def detect(gray, cascades):
    h, w = gray.shape
    for c in cascades:
        found = c.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(int(w * 0.11), int(w * 0.11)))
        found = [r for r in found if ROI[0] * h < r[1] + r[3] / 2 < ROI[1] * h and r[2] < w * 0.45]
        if len(found):
            return max(found, key=lambda r: r[2] * r[3])
    return None


def track(video, step=3):
    cap = cv2.VideoCapture(video)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cas = [cv2.CascadeClassifier(cv2.data.haarcascades + f) for f in
           ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml")]
    raw, i = {}, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            g = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            r = detect(g, cas)
            raw[i] = None if r is None else [int(v) for v in r]
        i += 1
    n = i
    keys = sorted(raw)
    good = [k for k in keys if raw[k]]
    out = {}
    for k in keys:
        if raw[k]:
            out[k] = raw[k]
            continue
        prev = max([g for g in good if g < k], default=None)
        nxt = min([g for g in good if g > k], default=None)
        if prev is None and nxt is None:
            continue
        if prev is None or nxt is None:
            out[k] = raw[prev if nxt is None else nxt]
            continue
        a = (k - prev) / (nxt - prev)
        out[k] = [round(raw[prev][j] * (1 - a) + raw[nxt][j] * a) for j in range(4)]
    # median-smooth (detector jitter) over 5 samples
    ks = sorted(out)
    arr = np.array([out[k] for k in ks], float)
    sm = arr.copy()
    for j in range(len(ks)):
        lo, hi = max(0, j - 2), min(len(ks), j + 3)
        sm[j] = np.median(arr[lo:hi], axis=0)
    return {"step": step, "fps": fps, "frames": n, "missing": [k for k in keys if not raw[k]],
            "boxes": {str(k): [int(v) for v in sm[j]] for j, k in enumerate(ks)}}


if __name__ == "__main__":
    step = int(sys.argv[sys.argv.index("--step") + 1]) if "--step" in sys.argv else 3
    res = track(sys.argv[1], step)
    json.dump(res, open(sys.argv[2], "w"))
    print(f"{len(res['boxes'])} samples, {len(res['missing'])} interpolated, {res['frames']} frames")
