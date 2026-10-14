#!/usr/bin/env python3
"""Per-frame cut-out cache for the assembled A-roll: the fast cut-out the compiled styles use (editorial-ui set
frames, behind-the-head heroes). Same person model as the hyperframes backend of cutout.py (u2net_human_seg, 320 px),
run on the Neural Engine (CoreML), one small mask per frame, cached per A-roll content hash, so a new plan never redoes
a frame and a crash resumes where it stopped.

  cutout_cache.py run <project> [--need work/cutout_need.json] [--follow] [--all] [--json]
        compute missing masks. --need: only the frames listed there ({"frames": [[f0, f1], ...]} half-open spans).
        --follow: start before the plan exists (pipeline.py): frames in order until the need file appears, then only
        the needed ones; exits when every needed frame is cached.
  cutout_cache.py status <project> [--need ...]        cached / needed counts (JSON)
  cutout_cache.py span <project> <f0> <f1>             RGBA VP9 webm of frames f0..f1 for a hero matte (cached)

Cache: <project>/work/cutout/<key>/m<NNNNN>.png (320x320 mask, uint8), key = model + aroll content hash.
alpha(cache, n) -> full-size float alpha (cubic upsample of the mask, like hyperframes; guided refine is opt-in).
Measured on the EDIT reel (M4 Pro): ~105 ms per frame (ANE) vs ~140 ms for `hyperframes remove-background` and
17-30 s for BiRefNet-portrait ONNX on CPU (matte_infer.py); see references/gotchas.md.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

FPS, W, H, NET = 30, 1080, 1920, 320
MODEL_ID = "u2net_human_seg-320"
MODEL_PATHS = [os.environ.get("REEL_ROOM_CUTOUT_MODEL", ""), str(Path.home() / ".u2net" / "u2net_human_seg.onnx"),
               str(Path.home() / ".cache" / "hyperframes" / "background-removal" / "models" / "u2net_human_seg.onnx")]
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
CPU_THREADS = 6
NEED_POLL = 30          # frames between checks for the need file in --follow mode
GF_R, GF_EPS = 6, 2e-3  # guided filter (half resolution): radius px, edge sensitivity


class CutoutError(RuntimeError):
    """The cut-out cannot run (no model, no A-roll). The message says what to fix."""


# ----------------------------------------------------------------------------------------------- cache layout
def aroll(proj: Path) -> Path:
    return Path(proj) / "assets" / "aroll.mp4"


def cache_dir(proj: Path) -> Path:
    """work/cutout/<model + aroll content hash>: a re-assembled A-roll gets a new folder, a new plan never does."""
    src = aroll(proj)
    if not src.exists():
        raise CutoutError(f"{src} not found: run assemble.py first")
    key = C.content_hash(src)[:16]
    return Path(proj) / "work" / "cutout" / f"{MODEL_ID}-{key}"


def mask_path(cdir: Path, n: int) -> Path:
    return cdir / f"m{n:05d}.png"


def frame_count(proj: Path) -> int:
    segs = C.read_json(Path(proj) / "segments.json", [])
    if segs:
        return max(s["frame"] + s["frames"] for s in segs)
    return int(round(C.probe(str(aroll(proj)))["dur"] * FPS))


def read_need(path) -> set | None:
    """{"frames": [[f0, f1], ...]} -> set of frame numbers (None when the file does not exist yet)."""
    p = Path(path) if path else None
    if not p or not p.exists():
        return None
    data = C.read_json(p, {})
    out = set()
    for span in data.get("frames", []):
        f0, f1 = int(span[0]), int(span[1])
        out.update(range(max(0, f0), max(f0, f1)))
    return out


def write_need(proj: Path, spans: list, why: dict | None = None) -> Path:
    """Merge spans into work/cutout_need.json (the compiler writes it, the worker reads it)."""
    p = Path(proj) / "work" / "cutout_need.json"
    spans = sorted([int(a), int(b)] for a, b in spans if int(b) > int(a))
    C.write_json(p, {"frames": spans, "why": why or {}, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return p


def missing(cdir: Path, frames) -> list:
    return [n for n in sorted(frames) if not mask_path(cdir, n).exists()]


# ----------------------------------------------------------------------------------------------- model
def find_model() -> str:
    m = next((p for p in MODEL_PATHS if p and os.path.exists(p)), None)
    if not m:
        raise CutoutError("no u2net_human_seg.onnx found: run `npx --yes hyperframes@0.8.34 remove-background` once "
                          "(it downloads the model) or set REEL_ROOM_CUTOUT_MODEL")
    return m


def sessions(model: str) -> list:
    """Neural Engine session (~105 ms/frame) plus a CPU session running beside it (~280 ms/frame): ~80 ms/frame
    together on an M4 Pro. CPU only where CoreML is missing."""
    import onnxruntime as ort
    ort.set_default_logger_severity(3)
    so = C._RL.ort_options(threads=CPU_THREADS)        # intra <= RR_MAX_THREADS, inter 1 (engine/rrlimits.py)
    cpu = ort.InferenceSession(model, so, providers=["CPUExecutionProvider"])
    if "CoreMLExecutionProvider" not in ort.get_available_providers():
        return [cpu]
    ane = ("CoreMLExecutionProvider", {"ModelFormat": "NeuralNetwork", "MLComputeUnits": "CPUAndNeuralEngine"})
    ane_so = C._RL.ort_options(threads=2)               # the ANE session only feeds the Neural Engine
    return [ort.InferenceSession(model, ane_so, providers=[ane, "CPUExecutionProvider"]), cpu]


class Infer:
    """Inference threads (one per session) fed from one queue; masks are written as they finish."""

    def __init__(self, sess: list, cdir: Path):
        self.q, self.cdir, self.done, self.lock = queue.Queue(maxsize=8), cdir, 0, threading.Lock()
        self.threads = [threading.Thread(target=self._run, args=(s,), daemon=True) for s in sess]
        for t in self.threads:
            t.start()

    def _run(self, sess):
        while True:
            job = self.q.get()
            if job is None:
                return
            _save(self.cdir, job[0], infer(sess, job[1]))
            with self.lock:
                self.done += 1

    def put(self, n, rgb):
        self.q.put((n, rgb))

    def close(self) -> int:
        for _ in self.threads:
            self.q.put(None)
        for t in self.threads:
            t.join()
        return self.done


def infer(sess, rgb320):
    """uint8 320x320x3 -> uint8 320x320 mask (same pre/post as hyperframes: max-pixel scale, min-max normalise)."""
    import numpy as np
    x = rgb320.astype(np.float32) / max(1, int(rgb320.max()))
    x = ((x - np.array(MEAN, np.float32)) / np.array(STD, np.float32)).transpose(2, 0, 1)[None]
    out = sess.run(None, {sess.get_inputs()[0].name: x.astype(np.float32)})[0][0, 0]
    lo, hi = float(out.min()), float(out.max())
    return ((out - lo) / ((hi - lo) or 1.0) * 255 + 0.5).astype(np.uint8)


# ----------------------------------------------------------------------------------------------- worker
def _decoder(src: Path, q: queue.Queue, stop: threading.Event):
    """Every frame of the A-roll at 320x320 into q as (n, rgb); None at the end."""
    import numpy as np
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-an", "-vf", f"scale={NET}:{NET}:flags=lanczos",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)    # the pipe closes early once the needed frames are done
    size, n = NET * NET * 3, 0
    try:
        while not stop.is_set():
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            q.put((n, np.frombuffer(buf, np.uint8).reshape(NET, NET, 3)))
            n += 1
    finally:
        q.put(None)
        p.kill()
        p.wait()


def _save(cdir: Path, n: int, mask) -> None:
    import cv2
    tmp = cdir / f".m{n:05d}.tmp.png"
    cv2.imwrite(str(tmp), mask)
    os.replace(tmp, mask_path(cdir, n))


def _status(proj: Path, **kw) -> None:
    C.write_json(Path(proj) / "work" / "cutout.status.json", {"engine": "cache", "model": MODEL_ID, **kw,
                                                              "updated": time.strftime("%Y-%m-%dT%H:%M:%S")})


def run(proj, need_file=None, follow=False, everything=False, log=print) -> dict:
    """Fill the cache. Returns {"computed", "needed", "secs", "fps"}."""
    proj = Path(proj)
    cdir = cache_dir(proj)
    cdir.mkdir(parents=True, exist_ok=True)
    total = frame_count(proj)
    need = set(range(total)) if everything else read_need(need_file)
    if need is None and not follow:
        raise CutoutError("no need file yet: pass --need <file>, --follow or --all")
    todo = None if need is None else set(missing(cdir, need))
    if todo == set():
        _status(proj, state="done", computed=0, needed=len(need))
        return {"computed": 0, "needed": len(need), "secs": 0.0, "fps": None}
    t0 = time.time()
    pool = Infer(sessions(find_model()), cdir)
    q, stop = queue.Queue(maxsize=64), threading.Event()
    threading.Thread(target=_decoder, args=(aroll(proj), q, stop), daemon=True).start()
    got = _loop(pool, proj, cdir, q, todo, need_file if follow else None, total, log)
    need = got if got is not None else need
    stop.set()
    done = pool.close()
    secs = round(time.time() - t0, 1)
    n_need = len(need) if need is not None else total
    _status(proj, state="done", computed=done, needed=n_need, seconds=secs)
    return {"computed": done, "needed": n_need, "secs": secs, "fps": round(done / secs, 1) if secs else None}


def _loop(pool, proj, cdir, q, todo, follow_file, total, log):
    """Dispatch decoded frames: everything uncached until the need file appears (follow), then only `todo`.
    Returns the need set (None when it never appeared)."""
    last, need = time.time(), None
    while True:
        item = q.get()
        if item is None:
            return need
        n, rgb = item
        if todo is None and follow_file and n % NEED_POLL == 0:
            need = read_need(follow_file)
            todo = None if need is None else {f for f in missing(cdir, need) if f >= n}
        if todo is not None:
            if not todo:
                return need
            if n not in todo:
                continue
            todo.discard(n)
        if mask_path(cdir, n).exists():
            continue
        pool.put(n, rgb)
        if time.time() - last > 15:
            last = time.time()
            _status(proj, state="running", computed=pool.done, frame=n, total=total,
                    left=len(todo) if todo is not None else None)
            log(f"[cutout] frame {n}/{total}, {pool.done} computed" + (f", {len(todo)} needed left" if todo else ""))


# ----------------------------------------------------------------------------------------------- waiting
WAIT_ENV = "REEL_CUTOUT_WAIT"      # pipeline.py sets it: consumers wait for masks the worker is still computing


def waiting() -> bool:
    return os.environ.get(WAIT_ENV) == "1"


def wait_for(proj, frames, timeout: float = 900.0, poll: float = 0.4) -> None:
    """Block until every mask in `frames` is cached (the parallel worker writes them in order). Raises when the
    worker failed or the timeout passes."""
    cdir, t0 = cache_dir(Path(proj)), time.time()
    left = missing(cdir, frames)
    while left:
        st = C.read_json(Path(proj) / "work" / "cutout.status.json", {})
        if st.get("state") == "failed":
            raise CutoutError("the cut-out worker failed: see work/cutout.log")
        if time.time() - t0 > timeout:
            raise CutoutError(f"timed out waiting for {len(left)} cut-out masks")
        time.sleep(poll)
        left = [n for n in left if not mask_path(cdir, n).exists()]


def wait_done(proj, timeout: float = 900.0) -> None:
    """Block until the worker reports done (the render never starts next to the cut-out)."""
    t0 = time.time()
    while C.read_json(Path(proj) / "work" / "cutout.status.json", {}).get("state") not in ("done", "failed"):
        if time.time() - t0 > timeout:
            raise CutoutError("timed out waiting for the cut-out worker")
        time.sleep(0.4)


# ----------------------------------------------------------------------------------------------- full-size alpha
def guided(guide, src, r=GF_R, eps=GF_EPS):
    """Edge-aware refinement (He et al. guided filter, grey guide), opt-in (alpha(refine=True))."""
    import cv2
    k = (2 * r + 1, 2 * r + 1)
    mean = lambda x: cv2.boxFilter(x, -1, k)  # noqa: E731
    mi, mp = mean(guide), mean(src)
    a = (mean(guide * src) - mi * mp) / (mean(guide * guide) - mi * mi + eps)
    b = mp - a * mi
    return mean(a) * guide + mean(b)


def alpha(cdir: Path, n: int, rgb=None, refine: bool = False):
    """Float32 HxW alpha for frame n (None when the mask is not cached): a cubic upsample of the 320 px mask (what
    hyperframes does). refine=True adds a guided filter on rgb; measured on the EDIT reel it pulls a busy room into
    the edge, so it stays off by default (bake.py refines the edge itself)."""
    import cv2
    import numpy as np
    p = mask_path(cdir, n)
    if not p.exists():
        return None
    m = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
    if rgb is None or not refine:
        return np.clip(cv2.resize(m, (W, H), interpolation=cv2.INTER_CUBIC), 0, 1)
    half = cv2.resize(m, (W // 2, H // 2), interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(cv2.resize(rgb, (W // 2, H // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    ref = guided(g.astype(np.float32) / 255, half)
    return np.clip(cv2.resize(ref, (W, H), interpolation=cv2.INTER_LINEAR), 0, 1)


# ----------------------------------------------------------------------------------------------- hero matte spans
def span_rel(f0: int, f1: int) -> str:
    return f"assets/matte/span_{f0:05d}_{f1:05d}.webm"


def span_webm(proj, f0: int, f1: int) -> dict:
    """RGBA VP9 webm (speaker over transparency) of A-roll frames [f0, f1) for a hero's behind-the-head matte.
    Returns {"matte": rel path, "matte_start": f0 / 30}. Cached by span; masks must be cached first."""
    import numpy as np
    proj = Path(proj)
    cdir = cache_dir(proj)
    rel = span_rel(f0, f1)
    out = proj / rel
    if out.exists():
        return {"matte": rel, "matte_start": round(f0 / FPS, 5)}
    if waiting():
        wait_for(proj, range(f0, f1))
    gone = missing(cdir, range(f0, f1))
    if gone:
        raise CutoutError(f"span {f0}-{f1}: {len(gone)} masks not cached (run cutout_cache.py run first)")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.webm")
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(aroll(proj)), "-an", "-vf",
                            f"select=between(n\\,{f0}\\,{f1 - 1})", "-vsync", "0", "-f", "rawvideo", "-pix_fmt",
                            "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(_vp9_args(tmp), stdin=subprocess.PIPE)
    for n in range(f0, f1):
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        a = alpha(cdir, n, rgb)
        enc.stdin.write(np.dstack([rgb, (a * 255 + 0.5).astype(np.uint8)]).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.kill()
    dec.wait()
    if enc.returncode:
        raise CutoutError(f"span {f0}-{f1}: the webm encode failed")
    os.replace(tmp, out)
    return {"matte": rel, "matte_start": round(f0 / FPS, 5)}


def _vp9_args(out) -> list:
    """Realtime VP9 with alpha, tagged BT.709 like the A-roll (no colour shift where it overlaps the plate)."""
    return ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
            "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-deadline", "realtime",
            "-cpu-used", "8", "-row-mt", "1", "-auto-alt-ref", "0", "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv", "-f", "webm", str(out)]


# ----------------------------------------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["run", "status", "span"])
    ap.add_argument("project")
    ap.add_argument("frames", nargs="*", type=int)
    ap.add_argument("--need")
    ap.add_argument("--follow", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    need = a.need or str(proj / "work" / "cutout_need.json")
    try:
        if a.cmd == "run":
            out = run(proj, need, a.follow, a.all)
        elif a.cmd == "span":
            out = span_webm(proj, a.frames[0], a.frames[1])
        else:
            cdir, want = cache_dir(proj), read_need(need)
            out = {"cache": str(cdir), "cached": len(list(cdir.glob("m*.png"))) if cdir.exists() else 0,
                   "needed": len(want) if want is not None else None,
                   "missing": len(missing(cdir, want)) if want is not None else None}
    except Exception as exc:  # noqa: BLE001  (any failure must reach the waiting bake and render as "failed")
        if a.cmd == "run":
            _status(proj, state="failed", error=str(exc)[:300])
        print(f"cutout_cache: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
