"""Hair-accurate person matte for the editorial-ui set: BiRefNet (portrait) per frame, cached per frame.

Runs only on the frames that sit on the coloured set or a takeover page (room beats never need a matte). The model input is a crop of
the frame from `crop_top` down (the wall above the head is never the person), so the 1024x1024 network sees the
speaker at ~0.8x instead of ~0.53x vertical resolution. Alpha PNGs land in <project>/work/matte/raw/f{N:05d}.png.

Model lookup: $REEL_ROOM_MATTE_MODEL, then ~/.u2net/birefnet-portrait.onnx (rembg's cache), then
~/.reel-room/models/birefnet-portrait.onnx. No model -> caller falls back to assets/aroll_matte.webm.
"""
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

W, H = 1080, 1920
NET = 1024
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
MODEL_CANDIDATES = [os.environ.get("REEL_ROOM_MATTE_MODEL", ""),
                    os.path.expanduser("~/.u2net/birefnet-portrait.onnx"),
                    os.path.expanduser("~/.reel-room/models/birefnet-portrait.onnx")]

_SESS = None


def find_model():
    return next((p for p in MODEL_CANDIDATES if p and os.path.exists(p)), None)


def _session(model, threads):
    global _SESS
    if _SESS is None:
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        _SESS = ort.InferenceSession(model, so, providers=["CPUExecutionProvider"])
    return _SESS


def read_frames(video, frames):
    """Decode the video once, sequentially, and yield (n, bgr) for the wanted frame numbers only."""
    want = set(frames)
    if not want:
        return
    last = max(want)
    cmd = ["ffmpeg", "-v", "error", "-i", video, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = W * H * 3
    n = 0
    try:
        while n <= last:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            if n in want:
                yield n, np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            n += 1
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def _infer_one(job):
    model, threads, crop_top, n, path_in, path_out = job
    img = cv2.imread(path_in)
    crop = img[crop_top:]
    x = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), (NET, NET), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    s = _session(model, threads)
    out = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    a = 1.0 / (1.0 + np.exp(-out))
    a = cv2.resize(a, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_CUBIC)
    full = np.zeros((H, W), np.float32)
    full[crop_top:] = np.clip(a, 0, 1)
    cv2.imwrite(path_out, (full * 255 + 0.5).astype(np.uint8))
    os.remove(path_in)
    return n


def infer(project, video, frames, crop_top=520, workers=4, threads=3, log=print):
    """Matte every frame in `frames` that is not cached yet. Returns the cache dir."""
    model = find_model()
    if not model:
        return None
    raw = os.path.join(project, "work", "matte", "raw")
    tmp = os.path.join(project, "work", "matte", "in")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    todo = [n for n in sorted(set(frames)) if not os.path.exists(os.path.join(raw, f"f{n:05d}.png"))]
    log(f"matte: {len(frames)} set frames, {len(todo)} to compute ({os.path.basename(model)}, {workers}x{threads} threads)")
    if not todo:
        return raw
    t0, done = time.time(), 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = []
        for n, img in read_frames(video, todo):
            pin = os.path.join(tmp, f"f{n:05d}.png")
            cv2.imwrite(pin, img)
            futs.append(ex.submit(_infer_one, (model, threads, crop_top, n, pin, os.path.join(raw, f"f{n:05d}.png"))))
        for f in futs:
            f.result()
            done += 1
            if done % 20 == 0 or done == len(todo):
                el = time.time() - t0
                log(f"  matte {done}/{len(todo)}  {el:.0f}s  ~{el / done * (len(todo) - done):.0f}s left")
    return raw


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("usage: matte_infer.py <project> [--threads N] [--extra f1,f2,...]")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plan as _plan
    pl = _plan.Plan(sys.argv[1])
    fr = [f for s in pl.segs if s["scene"] in ("set", "takeover") for f in range(s["f0"], s["f1"])]
    if "--extra" in sys.argv:
        fr += [int(x) for x in sys.argv[sys.argv.index("--extra") + 1].split(",")]
    th = int(sys.argv[sys.argv.index("--threads") + 1]) if "--threads" in sys.argv else max(2, (os.cpu_count() or 4) - 2)
    sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine"))
    th = min(th, __import__("rrlimits").budget())     # engine-wide CPU cap (RR_MAX_THREADS)
    if not infer(pl.dir, pl.proj.p("assets", "aroll.mp4"), fr, workers=1, threads=th):
        raise SystemExit("no BiRefNet model found (see the module docstring); bake.py will use assets/aroll_matte.webm")
