"""Face position per segment of the assembled A-roll (used to place captions and the split layout).

Usage: headpos.py <project> [--json] [--step 6]
Reads   assets/aroll.mp4 + segments.json
Writes  work/facepos.json   {segment_id: {cy, cx, h, n}}   in aroll pixels (1080x1920)
          cy, cx = median face centre, h = median face height, n = number of sampled frames with a face
Method: OpenCV Haar cascade (frontal, with the alt2 cascade as a fallback), every 6th frame of each segment, the largest
face per frame, median over the segment. A segment with no detections borrows the nearest segment's values and is marked
"guess": true (n stays 0).
Overrides: project.json "face_fix": {"<seg id>": {"cx": 300, "cy": 705, "h": 150}} replaces a segment's values after
detection (marked "fixed": true). Use it only after looking at the frames, for a profile the cascade missed or a false
hit on a hand or a poster. It survives every re-run of headpos.py.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SCALE = 0.5   # detect on a half-size frame (fast), report in full-size pixels


def load_cascades(cv2):
    names = ['haarcascade_frontalface_default.xml', 'haarcascade_frontalface_alt2.xml']
    out = []
    for n in names:
        c = cv2.CascadeClassifier(cv2.data.haarcascades + n)
        if not c.empty():
            out.append(c)
    if not out:
        C.fail('OpenCV face models were not found.', 'Run doctor.py to reinstall opencv-python-headless.')
    return out


def detect(cv2, cascades, gray):
    for c in cascades:
        faces = c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(int(60 * SCALE), int(60 * SCALE)))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            k = 1 / SCALE
            return (x + w / 2) * k, (y + h / 2) * k, h * k
    return None


def main():
    ap = argparse.ArgumentParser(description='Face centre/height per segment -> work/facepos.json')
    ap.add_argument('project')
    ap.add_argument('--step', type=int, default=6, help='sample every Nth frame')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    proj = C.need_project(a.project, ['segments.json'], a.json)
    aroll = proj / 'assets' / 'aroll.mp4'
    if not aroll.exists():
        C.fail('assets/aroll.mp4 does not exist yet.', 'Run assemble.py first.', a.json)
    try:
        import cv2
    except ImportError:
        C.fail('OpenCV is not installed.', 'Run doctor.py (it installs opencv-python-headless in the Reel Room venv).', a.json)
    t0 = time.time()
    segs = C.read_json(proj / 'segments.json')
    cascades = load_cascades(cv2)
    cap = cv2.VideoCapture(str(aroll))
    if not cap.isOpened():
        C.fail(f'Could not open {aroll}.', 'Re-run assemble.py.', a.json)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    samples = {s['id']: [] for s in segs}
    bounds = [(s['id'], s['frame'], s['frame'] + s['frames']) for s in segs]
    idx = 0
    bi = 0
    while True:
        if not cap.grab():
            break
        while bi < len(bounds) - 1 and idx >= bounds[bi][2]:
            bi += 1
        sid, f0, f1 = bounds[bi]
        if f0 <= idx < f1 and (idx - f0) % a.step == 0:
            ok, frame = cap.retrieve()
            if ok:
                small = cv2.resize(frame, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
                r = detect(cv2, cascades, cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
                if r:
                    samples[sid].append(r)
        idx += 1
    cap.release()
    res = {}
    for s in segs:
        v = samples[s['id']]
        if v:
            res[s['id']] = {'cy': round(st.median(x[1] for x in v), 1), 'cx': round(st.median(x[0] for x in v), 1),
                            'h': round(st.median(x[2] for x in v), 1), 'n': len(v)}
    missing = [s['id'] for s in segs if s['id'] not in res]
    if missing and not res:
        C.fail('No face was found in the whole cut.', 'Check the footage: the speaker should face the camera.', a.json)
    order = [s['id'] for s in segs]
    for sid in missing:   # borrow from the nearest segment that has a face
        i = order.index(sid)
        near = min((o for o in order if o in res), key=lambda o: abs(order.index(o) - i))
        res[sid] = {**res[near], 'n': 0, 'guess': True}
    res = {sid: res[sid] for sid in order}
    pj = C.read_json(proj / 'project.json') if (proj / 'project.json').exists() else {}
    fixed = []
    for sid, v in (pj.get('face_fix') or {}).items():   # checked by eye: Haar missed a profile or fired on a hand
        if sid in res and all(k in v for k in ('cx', 'cy', 'h')):
            res[sid] = {'cx': float(v['cx']), 'cy': float(v['cy']), 'h': float(v['h']), 'n': res[sid]['n'], 'fixed': True}
            fixed.append(sid)
    C.write_json(proj / 'work' / 'facepos.json', res)
    if fixed:
        out.log(f'face_fix from project.json applied to {fixed}')
    out.log(f'faces: {len(segs) - len(missing)}/{len(segs)} segments detected '
            f'({sum(v["n"] for v in res.values())} sampled frames of {total}) in {time.time() - t0:.1f}s'
            + (f'; no face in {missing} (borrowed from a neighbour)' if missing else ''))
    out.result({'ok': True, 'command': 'headpos', 'segments': len(segs), 'missing': missing, 'facepos': res,
                'seconds': round(time.time() - t0, 1)})


if __name__ == '__main__':
    main()
