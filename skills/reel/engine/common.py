"""Shared helpers for the Reel Room engine. Keep this small: every engine script imports it.

Contents
  paths        HOME (~/.reel-room), CACHE, VENV, venv_python(), project folders
  platform     load_platform(), ffmpeg_bin(), ffprobe_bin() (platform.json first, then PATH)
  processes    run(cmd_list, ...) (never shell=True), ffmpeg(args), ffprobe_json(path)
  json         read_json(), write_json() (atomic)
  media        probe(path) -> {dur,w,h,fps,rotation,...} (w/h are DISPLAY size, rotation already applied)
  hashing      content_hash(path) (fast sampled blake2b: size + 16 chunks of 1 MB)
  words        load_words(proj, clip), cut_words(proj), norm(text)
  cli          Out (plain/--json output), fail(msg, fix) (plain-language error + fix), reexec_in_venv()
  whisper      whisper_model(name) (cached per process, int8)

Conventions: times are seconds (float), 30 fps cut frames, project = folder path. Words are {w,s,e,p}
(source time) in work/words_<clip>_fast.json / _precise.json; cut-time words are {text,start,end} in words.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FPS = 30
HOME = Path(os.environ.get("REEL_ROOM_HOME", Path.home() / ".reel-room"))
CACHE = HOME / "cache"
VENV = HOME / "venv"
HF_PIN = "hyperframes@0.8.34"
IS_WIN = os.name == "nt"

import rrlimits as _RL  # noqa: E402  engine-wide CPU budget (RR_MAX_THREADS): ffmpeg -threads, PATH shim, workers
if os.environ.get("RR_LIMITS_INSTALLED") != "1":
    _RL.install()
    os.environ["RR_LIMITS_INSTALLED"] = "1"


# ----------------------------------------------------------------------------- json
def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(str(p))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data, indent=1):
    """atomic write (temp file in the same folder, then replace)"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ----------------------------------------------------------------------------- venv / platform
def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def in_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


def reexec_in_venv():
    """Re-run the current script with the Reel Room venv python (faster-whisper etc. live there)."""
    if in_venv() or os.environ.get("REEL_ROOM_NO_VENV") == "1":
        return
    py = venv_python()
    if not py.exists():
        return  # doctor has not run yet: let the script continue and fail with a clear message if it needs a package
    env = dict(os.environ, REEL_ROOM_NO_VENV="1")
    sys.exit(subprocess.call([str(py)] + sys.argv, env=env))


def load_platform() -> dict:
    return read_json(HOME / "platform.json", default={})


def _tool(name):
    pf = load_platform()
    p = pf.get(name)
    if p and Path(p).exists():
        return p
    return shutil.which(name) or name


def ffmpeg_bin() -> str:
    return _RL.shim_bin("ffmpeg") or _tool("ffmpeg")      # the shim adds -threads + nice


def ffprobe_bin() -> str:
    return _RL.shim_bin("ffprobe") or _tool("ffprobe")


def hf_cmd() -> list:
    """the pinned HyperFrames command as a list, e.g. ['npx','--yes','hyperframes@0.8.34']"""
    hf = load_platform().get("hf")
    return list(hf) if hf else [shutil.which("npx") or "npx", "--yes", HF_PIN]


# ----------------------------------------------------------------------------- processes
def nice_prefix(level: int = 10) -> list:
    """['nice', '-n', '10'] for a heavy child process; [] on Windows (no nice there)."""
    return [] if IS_WIN or not shutil.which("nice") else ["nice", "-n", str(level)]


def run(cmd, check=True, capture=True, timeout=None, cwd=None, env=None):
    """subprocess.run on a LIST (never a shell string). Returns CompletedProcess with text stdout/stderr."""
    if isinstance(cmd, str):
        raise TypeError("run() takes a list, not a shell string")
    return subprocess.run([str(c) for c in cmd], check=check, capture_output=capture, text=True,
                          timeout=timeout, cwd=cwd, env=env)


def ffmpeg(args, check=True, timeout=None):
    """run ffmpeg quietly with a list of args (after the binary). Errors raise with ffmpeg's own message."""
    cmd = _RL.wrap([ffmpeg_bin(), "-hide_banner", "-v", "error", "-y"] + [str(a) for a in args])   # -threads
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1])
    return r


def ffprobe_json(path, *extra) -> dict:
    cmd = _RL.wrap([ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", *extra, str(path)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe could not read {path}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout or "{}")


# ----------------------------------------------------------------------------- media
def _fps(s):
    try:
        a, b = str(s).split("/")
        return float(a) / float(b) if float(b) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path) -> dict:
    """{dur,w,h,fps,rotation,has_audio,vcodec,coded_w,coded_h}. w/h are the size AS DISPLAYED (rotation applied),
    which is the frame ffmpeg hands to filters (it auto-rotates)."""
    j = ffprobe_json(path)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"
              and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    if v is None:
        raise RuntimeError(f"no video stream in {path}")
    rot = 0
    tag = (v.get("tags") or {}).get("rotate")
    if tag is not None:
        try:
            rot = int(float(tag))
        except ValueError:
            pass
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    rot = ((rot % 360) + 360) % 360
    cw, ch = int(v["width"]), int(v["height"])
    w, h = (ch, cw) if rot in (90, 270) else (cw, ch)
    dur = float(j.get("format", {}).get("duration") or v.get("duration") or 0)
    return {"dur": round(dur, 3), "w": w, "h": h, "fps": round(_fps(v.get("avg_frame_rate") or v.get("r_frame_rate")), 3),
            "rotation": rot, "has_audio": any(s.get("codec_type") == "audio" for s in j["streams"]),
            "vcodec": v.get("codec_name"), "coded_w": cw, "coded_h": ch}


def content_hash(path) -> str:
    """fast content hash for big videos: size + 16 evenly spread 1 MB chunks (blake2b, 16 hex chars)"""
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.blake2b(digest_size=8)
    h.update(str(size).encode())
    chunk = 1 << 20
    with open(p, "rb") as f:
        if size <= chunk * 16:
            h.update(f.read())
        else:
            for i in range(16):
                f.seek((size - chunk) * i // 15)
                h.update(f.read(chunk))
    return h.hexdigest()


# ----------------------------------------------------------------------------- words
norm = lambda s: re.sub(r"[^a-z0-9']", "", str(s).lower())  # noqa: E731


def load_words(proj, clip, prefer=("precise", "medium", "fast")):
    """source-time words for a clip: precise (windowed medium.en) > legacy medium > fast. Returns (words, which)."""
    w = Path(proj) / "work"
    for kind in prefer:
        f = w / f"words_{clip}_{kind}.json"
        if f.exists():
            return drop_zero_length(read_json(f)), kind
    return [], None


NAMES_HINT = "Proper nouns: add them one per line to ~/.reel-room/names.txt (all projects) or <project>/names.txt."


def names_prompt(proj=None):
    """spelling hint for Whisper (initial_prompt) from ~/.reel-room/names.txt, <project>/names.txt (and ../names.txt)"""
    seen, names = set(), []
    files = [HOME / "names.txt"]
    if proj is not None:
        files += [Path(proj) / "names.txt", Path(proj).resolve().parent / "names.txt"]
    for f in files:
        if f.exists():
            for n in f.read_text(encoding="utf-8").splitlines():
                n = n.strip()
                if n and n.lower() not in seen:
                    seen.add(n.lower()); names.append(n)
    return (", ".join(names)[:400]) or None


def drop_zero_length(words):
    """Whisper sometimes returns words with no duration; they break cut anchors and captions"""
    return [w for w in words if w["e"] - w["s"] > 0.001]


def best_words(proj, clip):
    """source-time words for captions: precise (medium.en) words inside the precise windows
    (work/words_<clip>_precise.windows.json, written by splice words), fast (small.en) words everywhere else."""
    w = Path(proj) / "work"
    prec, _ = load_words(proj, clip, prefer=("precise", "medium"))
    fast = read_json(w / f"words_{clip}_fast.json", default=[]) if (w / f"words_{clip}_fast.json").exists() else []
    if not prec:
        return fast
    wf = w / f"words_{clip}_precise.windows.json"
    wins = read_json(wf) if wf.exists() else [[min(x["s"] for x in prec), max(x["e"] for x in prec)]]
    inside = lambda t: any(a <= t < b for a, b in wins)  # noqa: E731
    rest = [x for x in fast if not inside((x["s"] + x["e"]) / 2)]
    return sorted(prec + rest, key=lambda x: x["s"])


def layout(edl) -> list:
    """frame layout of an EDL (pure function): [{**seg, frame, frames, src_in, src_out}]"""
    out, f = [], 0
    for s in edl:
        n = max(1, round((s["out"] - s["in"]) * FPS))
        out.append({**s, "src_in": s["in"], "src_out": s["out"], "frame": f, "frames": n})
        f += n
    return out


def cut_words(proj, segments=None, edl=None) -> list:
    """cut-time words [{text,start,end}] built from source words + segments (used when words.json does not exist yet).
    A word belongs to a segment when its centre lies inside the segment's source range."""
    proj = Path(proj)
    segments = segments or read_json(proj / "segments.json")
    cache, res = {}, []
    for s in segments:
        c = s["clip"]
        if c not in cache:
            cache[c] = best_words(proj, c)
        a, b, f0 = s["src_in"], s["src_out"], s["frame"] / FPS
        for w in cache[c]:
            mid = (w["s"] + w["e"]) / 2
            if a <= mid < b:
                res.append({"text": w["w"], "start": round(f0 + max(w["s"], a) - a, 3),
                            "end": round(f0 + min(w["e"], b) - a, 3)})
    return res


# ----------------------------------------------------------------------------- cli
class Out:
    """Plain output by default; with --json, progress goes to stderr and one JSON object goes to stdout."""

    def __init__(self, json_mode=False):
        self.json = json_mode

    def log(self, *a):
        print(*a, file=sys.stderr if self.json else sys.stdout, flush=True)

    def result(self, data: dict):
        if self.json:
            print(json.dumps(data, ensure_ascii=False))


def fail(msg, fix="", json_mode=False, code=2):
    """plain-language error + the fix, then exit"""
    if json_mode or "--json" in sys.argv:
        print(json.dumps({"ok": False, "error": msg, "fix": fix}))
    else:
        print(f"ERROR: {msg}" + (f"\nFIX: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(code)


def need_project(proj, files=(), json_mode=False):
    p = Path(proj).expanduser()
    if not p.is_dir():
        fail(f"Project folder not found: {p}", "Pass the project folder (it holds edl.json, sources.json, work/, assets/).", json_mode)
    for f in files:
        if not (p / f).exists():
            hint = {"edl.json": "Write the edit list first (one entry per kept line).",
                    "sources.json": "Run ingest.py first: it writes sources.json.",
                    "segments.json": "Run assemble.py first: it writes segments.json."}.get(f, "Run the earlier pipeline step that creates it.")
            fail(f"Missing {f} in {p}", hint, json_mode)
    return p


def source_paths(proj) -> dict:
    """{clip: abs path}. sources.json is the list form [{clip,path,...}] (legacy dict form {clip: path} also accepted)"""
    s = read_json(Path(proj) / "sources.json")
    if isinstance(s, dict):
        return {k: v for k, v in s.items()}
    return {x["clip"]: x["path"] for x in s}


def source_info(proj) -> dict:
    s = read_json(Path(proj) / "sources.json")
    if isinstance(s, dict):
        return {k: {"clip": k, "path": v} for k, v in s.items()}
    return {x["clip"]: x for x in s}


# ----------------------------------------------------------------------------- whisper
_MODELS = {}


def whisper_model(name: str, workers: int = 1):
    """faster-whisper model, int8, loaded once per process (needs the venv). workers>1 lets several threads
    transcribe at once (use with a ThreadPoolExecutor of the same size)."""
    name_key = (name, workers)
    if name_key not in _MODELS:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            fail("faster-whisper is not installed.", f"Run: {sys.executable} {Path(__file__).parent / 'doctor.py'}")
        kw = {"num_workers": workers, "cpu_threads": max(2, (os.cpu_count() or 8) // workers // 2)} if workers > 1 else {}
        if _RL.max_threads():          # CPU budget (rrlimits); faster-whisper's own default is 4 threads
            kw["cpu_threads"] = min(kw.get("cpu_threads") or 4, _RL.whisper_threads(workers=workers))
        _MODELS[name_key] = WhisperModel(name, compute_type="int8", **kw)
    return _MODELS[name_key]
