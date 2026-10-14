#!/usr/bin/env python3
"""Reel Room BiRefNet person matte: high quality hair and edge cutout for assets/aroll_matte.webm.

Used by cutout.py --engine birefnet (public entry: run()). Also a small CLI:
  python matte_birefnet.py check                  which BiRefNet Python is used, and whether the model is cached
  python matte_birefnet.py seed-cache <hf_dir>    copy an existing Hugging Face cache of the model into ours
  python matte_birefnet.py infer ...              internal: the inference subprocess (run by run())

Pipeline (streaming, no PNG dumps)
  1. infer (runs in a Python with torch + transformers, see resolve_python()): ffmpeg decodes aroll.mp4 to rgb24 at
     the model size, BiRefNet predicts alpha per frame, alpha is written as lossless FFV1 gray video in parts of
     CHUNK frames under work/matte_alpha/. A crash keeps every finished part; the next run resumes after them.
  2. finalize (runs in the Reel Room venv, numpy + cv2): plate + alpha are streamed with a 3 frame window, edges are
     cleaned (temporal median where the plate is static, 1 px erode, 0.8 px feather, blur-fusion foreground colour,
     despill clamp) and RGBA is piped into libvpx-vp9 yuva420p (alpha_mode=1).

Sources: adapted from the earlier matte work (run_birefnet.py, finalize.py) + resumable birefnet_dir.py.
Model: BiRefNet (ZhengPeng7/BiRefNet_HR-matting), MIT licence, by ZhengPeng7, https://github.com/ZhengPeng7/BiRefNet
Foreground colour: blur-fusion from Forte and Pitie 2021, "Approximate Fast Foreground Colour Estimation" (ICIP 2021).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if __name__ == "__main__" and sys.argv[1:2] == ["infer"] and sys.path and os.path.abspath(sys.path[0] or ".") == HERE:
    sys.path.pop(0)                  # the inference venv imports torch: engine files must not shadow its modules

try:
    import numpy as np
except ImportError:  # the finalize side reports this with a fix in _need_cv()
    np = None
try:
    import cv2
except ImportError:  # the inference venv does not need cv2
    cv2 = None

HOME = Path(os.environ.get("REEL_ROOM_HOME", Path.home() / ".reel-room"))
MODEL_ID = "ZhengPeng7/BiRefNet_HR-matting"
MODEL_DIR = "models--" + MODEL_ID.replace("/", "--")
QUALITY_RES = {"fast": (1024, 576), "balanced": (1536, 864), "best": (2048, 1152)}  # portrait H x W, multiples of 32
CHUNK = 150                      # frames per FFV1 alpha part (5 s at 30 fps)
FPS, CRF = 30, 18
HEARTBEAT_S = int(os.environ.get("REEL_HEARTBEAT_S", "30"))
ERODE_PX, FEATHER_SIGMA, MOTION, DESPILL_R, FUSION_R = 1, 0.8, 0.06, 12, (90, 6)
INFER_SHARE = 90.0               # percent of the job spent in inference (rest is finalize)
SETUP = ("python3 -m venv ~/.reel-room/birefnet && "
         "~/.reel-room/birefnet/bin/pip install torch transformers timm kornia einops pillow numpy")


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- interpreter + cache
def python_candidates(env=None, home=HOME):
    """Ordered candidates: REEL_ROOM_BIREFNET_PY, platform.json birefnet_py, ~/.reel-room/birefnet python."""
    env = os.environ if env is None else env
    out = []
    if env.get("REEL_ROOM_BIREFNET_PY"):
        out.append(("REEL_ROOM_BIREFNET_PY", env["REEL_ROOM_BIREFNET_PY"]))
    try:
        with open(Path(home) / "platform.json", encoding="utf-8") as f:
            val = json.load(f).get("birefnet_py")
        if val:
            out.append(("platform.json birefnet_py", str(val)))
    except (OSError, ValueError):
        pass
    out.append(("default", str(Path(home) / "birefnet" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))
    return out


def has_torch(py):
    try:
        return os.path.isfile(py) and subprocess.run([py, "-B", "-c", "import torch, transformers"],
                                                     capture_output=True, timeout=180).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_python(env=None, home=HOME, check=has_torch):
    """First candidate that can import torch + transformers, else RuntimeError with the setup commands."""
    tried = []
    for label, py in python_candidates(env, home):
        if check(py):
            return py
        tried.append(f"{label}={py}")
    raise RuntimeError("no Python with torch + transformers for BiRefNet (tried " + ", ".join(tried) + "). "
                       f"Set it up once: {SETUP} . Or point REEL_ROOM_BIREFNET_PY at an existing one.")


def hf_home(env=None):
    return Path((os.environ if env is None else env).get("HF_HOME") or (HOME / "models" / "hf"))


def model_cached(hf_dir):
    snaps = Path(hf_dir) / "hub" / MODEL_DIR / "snapshots"
    return any((s / "model.safetensors").exists() for s in snaps.glob("*")) if snaps.is_dir() else False


def infer_env(env=None):
    """Env for the inference subprocess: HF_HOME defaulted, offline when the model is already cached."""
    e = dict(os.environ if env is None else env)
    e.setdefault("HF_HOME", str(hf_home(e)))
    if model_cached(e["HF_HOME"]):
        e.setdefault("HF_HUB_OFFLINE", "1")
    e.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    return e


def _copy_shared_blobs(src_hub, src_model, dst_hub):
    """New HF layouts keep weights in hub/blobs and symlink them from the model folder: copy those targets too."""
    for link in src_model.rglob("*"):
        if not link.is_symlink():
            continue
        target = link.resolve()
        if src_model.resolve() in target.parents or src_hub.resolve() not in target.parents:
            continue
        dst = dst_hub / target.relative_to(src_hub.resolve())
        if not dst.exists() or dst.stat().st_size != target.stat().st_size:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dst)
    for marker in ("CACHEDIR.TAG", "blobs/.huggingface-shared-blobs"):
        if (src_hub / marker).is_file() and not (dst_hub / marker).exists():
            (dst_hub / marker).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_hub / marker, dst_hub / marker)


def seed_cache(src_hf, dst_hf=None):
    """Copy hub/<model> (+ the shared blobs it links) and modules/ from an existing HF cache. Reads src only."""
    src_hf, dst_hf = Path(src_hf).expanduser(), Path(dst_hf or hf_home()).expanduser()
    src_hub, dst_hub = src_hf / "hub", dst_hf / "hub"
    src_model = src_hub / MODEL_DIR
    if not src_model.is_dir():
        raise RuntimeError(f"{src_model} not found; pass the folder that contains hub/{MODEL_DIR}")
    if not model_cached(dst_hf):
        if (dst_hub / MODEL_DIR).exists():
            shutil.rmtree(dst_hub / MODEL_DIR)
        dst_hub.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_model, dst_hub / MODEL_DIR, symlinks=True)
        _copy_shared_blobs(src_hub, src_model, dst_hub)
    if (src_hf / "modules").is_dir():
        shutil.copytree(src_hf / "modules", dst_hf / "modules", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if not model_cached(dst_hf):
        raise RuntimeError(f"copied, but {dst_hub / MODEL_DIR} has no readable model.safetensors")
    return dst_hf


def model_res(quality, w, h):
    """(H, W) model input size for the quality; swapped for landscape footage."""
    if quality not in QUALITY_RES:
        raise RuntimeError(f"unknown quality {quality!r}, use one of {', '.join(QUALITY_RES)}")
    mh, mw = QUALITY_RES[quality]
    return (mw, mh) if w > h else (mh, mw)


# ---------------------------------------------------------------- finalize: pure numpy / cv2
def _need_cv():
    if np is None or cv2 is None:
        raise RuntimeError("finalize needs numpy + opencv in the Reel Room venv. "
                           "Fix: ~/.reel-room/venv/bin/pip install numpy opencv-python-headless")


def box(x, r):
    return cv2.blur(x, (r * 2 + 1, r * 2 + 1), borderType=cv2.BORDER_REFLECT)


def temporal_smooth(a_prev, a, a_next, g_prev, g, g_next, motion=MOTION):
    """Median of t-1, t, t+1 alpha, only where the plate (gray, 0..1) is static so real motion never ghosts."""
    med = np.maximum(np.minimum(a_prev, a), np.minimum(np.maximum(a_prev, a), a_next))  # median of 3, no sort
    diff = np.maximum(np.abs(g - g_prev), np.abs(g - g_next))
    still = cv2.GaussianBlur((diff < motion).astype(np.float32), (0, 0), 2)
    return np.clip(a * (1 - still) + med * still, 0, 1).astype(np.float32)


def erode(a, px=ERODE_PX):
    """1 px choke per iteration (3x3 min filter): drops the bright background rim."""
    if px <= 0:
        return a
    return cv2.erode(a, np.ones((3, 3), np.uint8), iterations=px)


def feather(a, sigma=FEATHER_SIGMA):
    if sigma <= 0:
        return np.clip(a, 0, 1)
    return np.clip(cv2.GaussianBlur(a, (0, 0), sigma), 0, 1)


def blur_fusion(img, al, fg, bg, r):
    """One blur-fusion step (Forte and Pitie 2021): solves I = aF + (1-a)B for F with box-blurred estimates."""
    a3 = al[..., None]
    b_fa = box(fg * a3, r) / (box(al, r)[..., None] + 1e-5)
    b_b1a = box(bg * (1 - a3), r) / (box(1 - al, r)[..., None] + 1e-5)
    fg = b_fa + a3 * (img - a3 * b_fa - (1 - a3) * b_b1a)
    return np.clip(fg, 0, 1), b_b1a


def estimate_fg(img, al, radii=FUSION_R):
    """Foreground colour for float RGB img (0..1) and alpha: two passes, large then small radius."""
    fg, bg = img.copy(), img.copy()
    fg, bg = blur_fusion(img, al, fg, bg, radii[0])
    fg, _ = blur_fusion(img, al, fg, bg, radii[1])
    return fg


def despill(fg, al, r=DESPILL_R):
    """Edge band luminance capped to 1.08x the local interior colour, then blended toward it at low alpha."""
    core = (al > 0.97).astype(np.float32)
    band = ((al > 0.01) & (al < 0.97)).astype(np.float32)[..., None]
    w = box(core, r)
    fc = box(fg * core[..., None], r) / (w[..., None] + 1e-5)
    has = (w > 0.02)[..., None]
    lf, lc = (cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2GRAY)[..., None] for x in (fg, fc))
    cap = np.where((lf > lc * 1.08) & (band > 0), (lc * 1.08) / (lf + 1e-5), 1.0)
    fd = np.where(has, fg * cap, fg)
    k = (1 - al)[..., None] * band * 0.6
    fd = np.where(has, fd * (1 - k) + fc * k, fd)
    return np.clip(fd, 0, 1).astype(np.float32)


def clean_frame(prev, cur, nxt):
    """cur/prev/nxt = (rgb float, gray float, alpha float) or None at the clip edges. Returns RGBA uint8."""
    img, g, al = cur
    if prev is not None and nxt is not None:
        al = temporal_smooth(prev[2], al, nxt[2], prev[1], g, nxt[1])
    al = feather(erode(al))
    fg = despill(estimate_fg(img, al), al)
    return (np.dstack([fg, al]) * 255 + 0.5).astype(np.uint8)


def windows(items):
    """Yield (prev, cur, next) over an iterator, None at the edges. Holds at most 3 items."""
    prev = cur = None
    for nxt in items:
        if cur is not None:
            yield prev, cur, nxt
        prev, cur = cur, nxt
    if cur is not None:
        yield prev, cur, None


# ---------------------------------------------------------------- streaming helpers
def read_frames(cmd, w, h, ch):
    """Yield uint8 frames (h, w, ch) from an ffmpeg rawvideo pipe."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = w * h * ch
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, ch) if ch > 1 else np.frombuffer(buf, np.uint8).reshape(h, w)
    finally:
        p.kill()
        p.wait()


def vp9_alpha_cmd(out, w, h):
    return ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(FPS),
            "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", str(CRF),
            "-auto-alt-ref", "0", "-row-mt", "1", "-metadata:s:v:0", "alpha_mode=1", "-f", "webm", out]


def ffv1_gray_cmd(out, w, h):
    return ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(FPS),
            "-i", "-", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gray", "-f", "matroska", out]


def part_path(parts, k, tmp=False):
    return os.path.join(parts, f"part_{k:04d}" + (".tmp.mkv" if tmp else ".mkv"))


def completed_parts(parts):
    """Count of consecutive finished parts from part_0000 (a gap means everything after it is redone)."""
    k = 0
    while os.path.isfile(part_path(parts, k)):
        k += 1
    return k


def prepare_parts(parts, src, res):
    """Keep finished parts only if they were made from this exact source + model size; drop temp parts."""
    st = os.stat(src)
    key = {"src": os.path.abspath(src), "size": st.st_size, "mtime": int(st.st_mtime), "res": list(res),
           "model": MODEL_ID, "chunk": CHUNK}
    meta = os.path.join(parts, "meta.json")
    try:
        with open(meta, encoding="utf-8") as f:
            same = json.load(f) == key
    except (OSError, ValueError):
        same = False
    if not same and os.path.isdir(parts):
        shutil.rmtree(parts)
    os.makedirs(parts, exist_ok=True)
    for name in os.listdir(parts):
        if name.endswith(".tmp.mkv"):
            os.remove(os.path.join(parts, name))
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(key, f)


# ---------------------------------------------------------------- inference subprocess (torch venv)
def pick_device(torch):
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    log("[birefnet] WARNING: no GPU (mps/cuda), running on cpu: this is very slow (many seconds per frame)")
    return "cpu"


def _close_part(enc, parts, k):
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"ffmpeg could not write alpha part {k}")
    os.replace(part_path(parts, k, tmp=True), part_path(parts, k))


def infer_main(src, parts, start, w, h, mh, mw):
    import torch
    from transformers import AutoModelForImageSegmentation
    dev = pick_device(torch)
    log(f"[birefnet] device {dev}, model {MODEL_ID} at {mh}x{mw}, starting at frame {start}")
    net = AutoModelForImageSegmentation.from_pretrained(MODEL_ID, trust_remote_code=True).to(dev).eval()
    dtype = next(net.parameters()).dtype
    mean = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)
    dec = ["ffmpeg", "-v", "error", "-i", src, "-an", "-vf", f"scale={mw}:{mh}:flags=bicubic",
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    i, enc, t0 = 0, None, time.time()
    with torch.inference_mode():
        for im in read_frames(dec, mw, mh, 3):
            if i < start:
                i += 1
                continue
            if enc is None:
                enc = subprocess.Popen(ffv1_gray_cmd(part_path(parts, i // CHUNK, tmp=True), w, h), stdin=subprocess.PIPE)
            x = torch.from_numpy(im.copy()).to(dev).permute(2, 0, 1)[None].float() / 255
            y = net(((x - mean) / std).to(dtype))[-1].float().sigmoid()
            y = torch.nn.functional.interpolate(y, size=(h, w), mode="bilinear", align_corners=False)
            enc.stdin.write((y[0, 0].clamp(0, 1) * 255).round().byte().cpu().numpy().tobytes())
            i += 1
            if i % CHUNK == 0:
                _close_part(enc, parts, i // CHUNK - 1)
                enc = None
            log(f"@@progress {i} {(i - start) / max(time.time() - t0, 1e-6):.3f}")
    if enc is not None:
        _close_part(enc, parts, (i - 1) // CHUNK)
    log(f"[birefnet] inference done: {i - start} frames in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- parent side (Reel Room venv)
def write_status(path, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kw["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(kw, f)
    os.replace(path + ".tmp", path)


def beat(status_path, t0, stage, pct, fps, eta, out=None):
    el = time.time() - t0
    size = os.path.getsize(out) / 1e6 if out and os.path.exists(out) else 0.0
    log(f"[cutout] birefnet {stage} {int(el // 60)}m{int(el % 60):02d}s elapsed, progress {pct:.0f}%, "
        f"{fps:.2f} fps, ETA {int(eta // 60)}m{int(eta % 60):02d}s" + (f", output {size:.1f} MB" if out else ""))
    write_status(status_path, state="running", engine="birefnet", stage=stage, elapsed_s=int(el),
                 percent=round(pct, 1), fps=round(fps, 3), eta_s=int(eta), output_mb=round(size, 1))


def _read_infer(proc, state):
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("@@progress"):
            _, done, fps = line.split()
            state["done"], state["fps"] = int(done), float(fps)
        elif line:
            state["tail"] = (state["tail"] + [line[:200]])[-4:]
            if line.startswith("[birefnet]"):
                log(line)


def run_infer(py, src, parts, start, total, w, h, res, status_path, t0):
    cmd = [py, "-B", os.path.abspath(__file__), "infer", src, parts, str(start), str(w), str(h), str(res[0]), str(res[1])]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            env=infer_env())
    state = {"done": start, "fps": 0.0, "tail": []}
    th = threading.Thread(target=_read_infer, args=(proc, state), daemon=True)
    th.start()
    last = time.time()
    try:
        while proc.poll() is None:
            time.sleep(1)
            if time.time() - last >= HEARTBEAT_S:
                last = time.time()
                fps = state["fps"]
                eta = (total - state["done"]) / fps * 1.1 if fps > 0 else 0
                beat(status_path, t0, "infer", INFER_SHARE * state["done"] / total, fps, eta)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
    th.join(timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"BiRefNet inference exited {proc.returncode}: " + " | ".join(state["tail"])
                           + f" (finished parts are kept in {parts}, rerun to resume)")


def _plates_and_alphas(src, parts, w, h):
    lst = os.path.join(parts, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for k in range(completed_parts(parts)):
            f.write(f"file '{os.path.basename(part_path(parts, k))}'\n")
    plates = read_frames(["ffmpeg", "-v", "error", "-i", src, "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], w, h, 3)
    alphas = read_frames(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-pix_fmt", "gray",
                          "-f", "rawvideo", "-"], w, h, 1)
    for p, a in zip(plates, alphas):
        img = p.astype(np.float32) / 255
        yield img, cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), a.astype(np.float32) / 255


def finalize(src, parts, out, total, w, h, status_path, t0):
    """Stream plate + alpha through the edge cleanup into a VP9 alpha WebM (raises if a frame is missing)."""
    enc = subprocess.Popen(vp9_alpha_cmd(out, w, h), stdin=subprocess.PIPE)
    n, ts, last = 0, time.time(), time.time()
    try:
        for prev, cur, nxt in windows(_plates_and_alphas(src, parts, w, h)):
            enc.stdin.write(clean_frame(prev, cur, nxt).tobytes())
            n += 1
            if time.time() - last >= HEARTBEAT_S:
                last = time.time()
                fps = n / max(last - ts, 1e-6)
                beat(status_path, t0, "finalize", INFER_SHARE + (100 - INFER_SHARE) * n / total, fps,
                     (total - n) / fps, out)
    finally:
        try:
            enc.stdin.close()
        except OSError:
            pass
        enc.wait()
    if enc.returncode != 0:
        raise RuntimeError("ffmpeg could not encode the VP9 alpha matte")
    if n != total:
        raise RuntimeError(f"finalize wrote {n} frames, aroll has {total}")


def run(src, out, status_path, total, w, h, quality):
    """cutout.py entry: BiRefNet matte of src into out (VP9 alpha WebM). Raises RuntimeError on failure."""
    _need_cv()
    py = resolve_python()
    res = model_res(quality, w, h)
    parts = os.path.join(os.path.dirname(status_path), "matte_alpha")
    prepare_parts(parts, src, res)
    start = min(total, completed_parts(parts) * CHUNK)
    t0 = time.time()
    log(f"[cutout] birefnet {MODEL_ID} at {res[0]}x{res[1]} ({quality}), {total} frames at {w}x{h}, python {py}"
        + (f", resuming after {start} frames" if start else ""))
    if not model_cached(infer_env()["HF_HOME"]):
        log("[cutout] model not cached yet: first run downloads about 450 MB from Hugging Face")
    write_status(status_path, state="running", engine="birefnet", stage="infer", elapsed_s=0,
                 percent=round(INFER_SHARE * start / total, 1), total_frames=total)
    if start < total:
        run_infer(py, src, parts, start, total, w, h, res, status_path, t0)
    log("[cutout] birefnet finalize: edge cleanup + VP9 alpha encode")
    finalize(src, parts, out, total, w, h, status_path, t0)
    shutil.rmtree(parts, ignore_errors=True)
    log(f"[cutout] birefnet finished in {int(time.time() - t0)}s")


# ---------------------------------------------------------------- CLI
def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if cmd == "infer" and len(args) == 7:
            infer_main(args[0], args[1], *map(int, args[2:]))
        elif cmd == "seed-cache" and len(args) == 1:
            log(f"seeded {seed_cache(args[0])}")
        elif cmd == "check":
            log(f"python: {resolve_python()}\nHF_HOME: {hf_home()}\nmodel cached: {model_cached(hf_home())}")
        else:
            print(__doc__)
            return 0 if cmd in ("", "-h", "--help") else 2
    except RuntimeError as e:
        print(f"matte_birefnet: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
