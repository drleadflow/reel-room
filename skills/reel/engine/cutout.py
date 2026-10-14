#!/usr/bin/env python3
"""Reel Room cutout: cut the speaker out of assets/aroll.mp4 so graphics can sit BEHIND the head.

  python cutout.py <project> [--engine auto|hyperframes|rembg|birefnet] [--quality fast|balanced|best] [--force] [--json]

Writes assets/aroll_matte.webm (VP9 with alpha, same frame count as aroll.mp4) and work/cutout.status.json.

Engines
  hyperframes  npx --yes hyperframes@0.8.34 remove-background (pinned, local model, uses CoreML/CUDA when present).
               About 0.8 s per frame on an Apple Silicon laptop: a 77 s reel (2316 frames) takes about 30 minutes.
  rembg        fallback when npx / the pinned CLI fails and the Python package `rembg` is importable
               (uses the u2net_human_seg model, frames streamed through ffmpeg, no big temp folders).
  auto         hyperframes first, then rembg.
  birefnet     opt-in, BiRefNet HR-matting (matte_birefnet.py): best hair and edges, slower (about 0.4 to 0.8 fps at
               --quality best on Apple Silicon). Needs a Python with torch + transformers; resumes after a crash.

This is a long job: run it in the background. A progress line is printed every 30 seconds
(elapsed time, percent when the tool reports it, size of the output so far) and mirrored to
work/cutout.status.json so Claude can poll it. After rendering the matte frame count is checked against the aroll
(ffprobe, decoded with libvpx-vp9 so the alpha plane is counted); a mismatch deletes the matte and exits non-zero.
The result is written to a temp file first and moved into place only when the check passes.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

HF_VERSION = "0.8.34"
HEARTBEAT_S = int(os.environ.get("REEL_HEARTBEAT_S", "30"))
FPS = 30
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def log(msg):
    print(msg, flush=True)


def die(msg, fix=""):
    print(f"cutout: {msg}" + (f"\n  Fix: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(1)


def write_status(path, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kw["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kw, f)
    os.replace(tmp, path)


def probe_frames(path, alpha=False):
    """Exact decoded frame count. alpha=True forces libvpx-vp9 so the alpha plane of a webm is handled."""
    cmd = ["ffprobe", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha else []) + [
        "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames,width,height",
        "-of", "json", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:] or "ffprobe failed")
    s = json.loads(r.stdout)["streams"][0]
    return int(s["nb_read_frames"]), int(s["width"]), int(s["height"])


# ---------------------------------------------------------------- hyperframes engine
def run_hyperframes(src, out, quality, status_path, total):
    cmd = ["npx", "--yes", f"hyperframes@{HF_VERSION}", "remove-background", src, "-o", out, "--quality", quality]
    if os.name == "nt":
        cmd[0] = "npx.cmd"
    log(f"[cutout] hyperframes {HF_VERSION}: {os.path.basename(src)} -> {os.path.basename(out)} ({total} frames)")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    state = {"last": "", "pct": None}

    def reader():
        for line in p.stdout:
            line = ANSI.sub("", line).strip()
            if not re.search(r"[A-Za-z0-9]", line) or "onnxruntime" in line:       # CoreML partition warnings are noise
                continue
            state["last"] = line[:160]
            m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", line)
            if m:
                state["pct"] = float(m.group(1))
            m = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if m and int(m.group(2)) == total:
                state["pct"] = 100.0 * int(m.group(1)) / total

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t0 = last_beat = time.time()
    while p.poll() is None:
        time.sleep(1)
        if time.time() - last_beat >= HEARTBEAT_S:
            last_beat = time.time()
            heartbeat(status_path, last_beat - t0, state, out)
    t.join(timeout=5)
    if p.returncode != 0:
        raise RuntimeError(f"hyperframes remove-background exited {p.returncode}: {state['last']}")


def heartbeat(status_path, elapsed, state, out):
    size = os.path.getsize(out) if os.path.exists(out) else 0
    pct = f"{state['pct']:.0f}%" if state["pct"] is not None else "n/a"
    log(f"[cutout] working {int(elapsed // 60)}m{int(elapsed % 60):02d}s elapsed, progress {pct}, output {size / 1e6:.1f} MB"
        + (f", last: {state['last']}" if state["last"] else ""))
    write_status(status_path, state="running", elapsed_s=int(elapsed), percent=state["pct"], output_mb=round(size / 1e6, 1))


# ---------------------------------------------------------------- rembg engine
def run_rembg(src, out, status_path, total, w, h):
    try:
        import numpy as np
        from rembg import new_session, remove
    except Exception as e:  # ImportError or a broken onnxruntime
        raise RuntimeError(f"rembg is not usable ({e}). Install it: pip install 'rembg[cpu]'")
    log(f"[cutout] rembg (u2net_human_seg) fallback, {total} frames at {w}x{h}")
    session = new_session("u2net_human_seg")
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0",
                            "-crf", "22", "-auto-alt-ref", "0", "-row-mt", "1", "-f", "webm", out],
                           stdin=subprocess.PIPE)
    from PIL import Image
    size, n, t0, last_beat = w * h * 3, 0, time.time(), time.time()
    state = {"last": "", "pct": 0.0}
    try:
        while True:
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            img = Image.frombytes("RGB", (w, h), buf)
            rgba = remove(img, session=session, post_process_mask=True)
            enc.stdin.write(np.asarray(rgba.convert("RGBA")).tobytes())
            n += 1
            state["pct"] = 100.0 * n / total
            if time.time() - last_beat >= HEARTBEAT_S:
                last_beat = time.time()
                heartbeat(status_path, time.time() - t0, state, out)
    finally:
        try:
            enc.stdin.close()
        except OSError:
            pass
        enc.wait()
        dec.kill()
        dec.wait()
    if enc.returncode != 0:
        raise RuntimeError("ffmpeg could not encode the matte")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Reel Room cutout (background matte)")
    ap.add_argument("project")
    ap.add_argument("--engine", choices=["auto", "hyperframes", "rembg", "birefnet"], default="auto")
    ap.add_argument("--quality", choices=["fast", "balanced", "best"], default="balanced")
    ap.add_argument("--force", action="store_true", help="redo the matte even if a valid one exists")
    ap.add_argument("--json", action="store_true", help="print the final result as JSON")
    a = ap.parse_args()
    project = os.path.abspath(a.project)
    src = os.path.join(project, "assets", "aroll.mp4")
    out = os.path.join(project, "assets", "aroll_matte.webm")
    status = os.path.join(project, "work", "cutout.status.json")
    if not os.path.isfile(src):
        die(f"{src} not found", "run assemble.py first, the cutout is made from the assembled aroll")
    try:
        total, w, h = probe_frames(src)
    except (RuntimeError, ValueError) as e:
        die(f"cannot read aroll.mp4: {e}", "run doctor.py to check ffmpeg")

    if os.path.exists(out) and not a.force:
        try:
            n, _, _ = probe_frames(out, alpha=True)
            if n == total:
                log(f"[cutout] matte already exists with {n} frames, nothing to do (use --force to redo)")
                write_status(status, state="done", frames=n, engine="existing")
                if a.json:
                    print(json.dumps({"ok": True, "path": out, "frames": n, "engine": "existing"}))
                return
        except (RuntimeError, ValueError):
            pass

    tmpdir = tempfile.mkdtemp(prefix="cutout_", dir=os.path.join(project, "work"))
    tmp_out = os.path.join(tmpdir, "aroll_matte.webm")
    write_status(status, state="running", elapsed_s=0, percent=0, total_frames=total)
    t0 = time.time()
    errors, engine_used = [], None
    order = {"auto": ["hyperframes", "rembg"], "hyperframes": ["hyperframes"], "rembg": ["rembg"],
             "birefnet": ["birefnet"]}[a.engine]
    for eng in order:
        try:
            if eng == "hyperframes":
                run_hyperframes(src, tmp_out, a.quality, status, total)
            elif eng == "birefnet":
                import matte_birefnet
                matte_birefnet.run(src, tmp_out, status, total, w, h, a.quality)
            else:
                run_rembg(src, tmp_out, status, total, w, h)
            engine_used = eng
            break
        except (RuntimeError, OSError) as e:
            errors.append(f"{eng}: {e}")
            log(f"[cutout] {eng} failed: {e}")
            if os.path.exists(tmp_out):
                os.remove(tmp_out)
    if not engine_used:
        write_status(status, state="failed", errors=errors)
        die("no cutout engine worked: " + " | ".join(errors),
            "check Node 22+ and internet for the first model download (python doctor.py), or pip install 'rembg[cpu]'")

    try:
        got, mw, mh = probe_frames(tmp_out, alpha=True)
    except (RuntimeError, ValueError) as e:
        write_status(status, state="failed", errors=[str(e)])
        die(f"the matte cannot be read back: {e}")
    if got != total or (mw, mh) != (w, h):
        os.remove(tmp_out)
        write_status(status, state="failed", errors=[f"matte has {got} frames at {mw}x{mh}, aroll has {total} at {w}x{h}"])
        die(f"frame count mismatch: matte has {got} frames at {mw}x{mh}, aroll has {total} at {w}x{h}",
            "rerun with --force; if it repeats, try --engine rembg")
    os.replace(tmp_out, out)
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass
    secs = int(time.time() - t0)
    write_status(status, state="done", frames=got, engine=engine_used, seconds=secs)
    log(f"[cutout] done: {out} ({got} frames = aroll, {os.path.getsize(out) / 1e6:.1f} MB, {engine_used}, {secs}s)")
    if a.json:
        print(json.dumps({"ok": True, "path": out, "frames": got, "engine": engine_used, "seconds": secs}))


if __name__ == "__main__":
    main()
