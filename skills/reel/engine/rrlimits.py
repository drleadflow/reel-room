"""Engine-wide CPU budget: one number caps every heavy thing the engine starts (shared machine, low RAM).

  RR_MAX_THREADS     env var, or project.json "machine": {"max_threads": N}; default about half the cores.
                     "off" (or 0) = no cap (the old behaviour, used to measure "before").
  ffmpeg / ffprobe   every call gets -threads (inputs and outputs) and -filter_threads, through
                     (a) common.ffmpeg / ffmpeg_bin() / ffprobe_bin() and (b) a PATH shim (work dir ~/.reel-room/shim)
                     that catches the direct subprocess calls and the ones hyperframes makes. The shim also runs
                     ffmpeg under nice 10.
  onnxruntime        ort_options() -> SessionOptions with intra/inter op limits (cutout_cache, matte_infer); rembg
                     reads OMP_NUM_THREADS, which install() sets.
  workers            render_workers(n) / pool_workers(n): worker counts follow the same budget.
  whisper            whisper_threads(): CTranslate2 cpu_threads.
install() exports the budget into os.environ (children inherit it). Pure stdlib: the shim imports this file with
python -S -I.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

ENV = "RR_MAX_THREADS"
NICE = 10
SHIM_DIR = Path(os.environ.get("REEL_ROOM_HOME", Path.home() / ".reel-room")) / "shim"
THREAD_ENVS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
               "NUMEXPR_NUM_THREADS")
# ffmpeg options that take NO value (everything else that starts with '-' takes exactly one)
FLAGS = {"-y", "-n", "-an", "-vn", "-sn", "-dn", "-shortest", "-nostdin", "-stdin", "-hide_banner", "-nostats",
         "-stats", "-copyts", "-start_at_zero", "-accurate_seek", "-noaccurate_seek", "-re", "-ignore_unknown",
         "-copy_unknown", "-benchmark", "-benchmark_all", "-dump", "-hex", "-xerror", "-debug_ts", "-autorotate",
         "-noautorotate", "-autoscale", "-noautoscale", "-bitexact", "-report", "-version", "-L", "-h", "-formats",
         "-codecs", "-encoders", "-decoders", "-filters", "-pix_fmts", "-layouts", "-sample_fmts", "-buildconf",
         "-show_format", "-show_streams", "-show_frames", "-show_packets", "-show_entries_all", "-count_frames",
         "-count_packets", "-show_chapters", "-show_programs", "-show_error", "-pretty", "-show_data"}


def cores() -> int:
    return os.cpu_count() or 4


def default_threads() -> int:
    return max(2, cores() // 2)


def _project_value(proj) -> object:
    if not proj:
        return None
    try:
        pj = json.loads((Path(proj) / "project.json").read_text())
    except (OSError, ValueError):
        return None
    return (pj.get("machine") or {}).get("max_threads")


def parse(value) -> int | None:
    """'off' / 0 -> None (no cap); a number -> that many threads (at least 1); anything else -> default."""
    if value is None or value == "":
        return default_threads()
    if str(value).strip().lower() in ("off", "none", "0", "false"):
        return None
    try:
        return max(1, int(float(value)))
    except ValueError:
        return default_threads()


def max_threads(proj=None) -> int | None:
    """The budget (None = uncapped). Env wins over project.json, project.json over the default."""
    raw = os.environ.get(ENV)
    return parse(raw if raw is not None else _project_value(proj))


def budget(proj=None) -> int:
    """The budget as a count (the whole machine when uncapped)."""
    return max_threads(proj) or cores()


def render_workers(requested: int | None, proj=None) -> int:
    """Render (Chrome) workers: never more than the budget."""
    n = requested or 6
    cap = max_threads(proj)
    return max(1, min(n, cap)) if cap else n


def pool_workers(requested: int, proj=None, per_worker: int = 1) -> int:
    """Process-pool size when each worker uses `per_worker` threads."""
    cap = max_threads(proj)
    return max(1, min(requested, cap // max(1, per_worker))) if cap else requested


def ffmpeg_threads() -> int | None:
    """-threads for one ffmpeg call: the per-job share when a pool set one (share()), else the budget."""
    cap = max_threads()
    v = os.environ.get("RR_FFMPEG_THREADS")
    if not cap or not v:
        return cap
    try:
        return max(1, min(cap, int(v)))
    except ValueError:
        return cap


def share(jobs: int) -> int | None:
    """A pool of `jobs` parallel ffmpeg calls splits the budget (children inherit RR_FFMPEG_THREADS)."""
    cap = max_threads()
    if not cap:
        return None
    n = max(1, cap // max(1, jobs))
    os.environ["RR_FFMPEG_THREADS"] = str(n)
    return n


def whisper_threads(proj=None, workers: int = 1) -> int:
    return max(1, budget(proj) // max(1, workers))


def ort_options(proj=None, threads: int | None = None):
    """onnxruntime SessionOptions within the budget (intra = threads, inter = 1)."""
    import onnxruntime as ort
    so = ort.SessionOptions()
    cap = max_threads(proj)
    n = threads or (cap or cores())
    so.intra_op_num_threads = max(1, min(n, cap) if cap else n)
    so.inter_op_num_threads = 1
    return so


# ---------------------------------------------------------------------------------------------- ffmpeg args
def _group_threads(argv: list, start: int, end: int, n: int) -> bool:
    """Lower an existing -threads inside argv[start:end] to n (0 = auto counts as above n). True when found."""
    for i in range(start, end - 1):
        if argv[i] == "-threads":
            try:
                v = int(argv[i + 1])
            except ValueError:
                v = 0
            argv[i + 1] = str(n if v <= 0 else min(v, n))
            return True
    return False


def _lower_all(argv: list, n: int) -> None:
    for i in range(len(argv) - 1):
        if argv[i] == "-threads":
            try:
                v = int(argv[i + 1])
            except ValueError:
                continue
            argv[i + 1] = str(n if v <= 0 else min(v, n))


def _files(argv: list) -> list:
    """[(index, 'in' | 'out')] of every input / output file token in an ffmpeg argv (binary excluded)."""
    out, i = [], 0
    while i < len(argv):
        tok = str(argv[i])
        if tok == "-i" and i + 1 < len(argv):
            out.append((i, "in"))
            i += 2
        elif tok.startswith("-") and tok != "-" and tok not in FLAGS:
            i += 2
        elif tok in FLAGS:
            i += 1
        else:
            out.append((i, "out"))
            i += 1
    return out


def ffmpeg_args(argv: list, n: int | None) -> list:
    """argv (no binary) with -threads n on every input and output and -filter_threads n. Existing larger values are
    lowered, smaller ones kept. n None = unchanged."""
    argv = [str(a) for a in argv]
    if not n or not any(a == "-i" for a in argv):
        return argv
    if "-threads" in argv:              # the caller placed its own: never add one, only lower the values above n
        _lower_all(argv, n)
        return argv if "-filter_threads" in argv else ["-filter_threads", str(n)] + argv
    res, prev = [], 0
    for idx, kind in _files(argv):
        if not _group_threads(argv, prev, idx, n):
            res += argv[prev:idx] + ["-threads", str(n)]
        else:
            res += argv[prev:idx]
        prev = idx + (2 if kind == "in" else 1)
        res += argv[idx:prev]
    res += argv[prev:]
    if "-filter_threads" not in res:
        res = ["-filter_threads", str(n)] + res
    if any(a in ("-filter_complex", "-lavfi", "-filter_complex_script") for a in res) and \
            "-filter_complex_threads" not in res:
        res = ["-filter_complex_threads", str(n)] + res
    return res


def ffprobe_args(argv: list, n: int | None) -> list:
    """ffprobe is left as it is: probing is cheap, and callers (HyperFrames) put the input first, where an added
    -threads becomes a second input ("Argument '7' provided as input filename"). It still runs under nice."""
    return [str(a) for a in argv]


def wrap(cmd: list, n: int | None = None) -> list:
    """A full command list (binary first): thread args added when the binary is ffmpeg / ffprobe."""
    n = ffmpeg_threads() if n is None else n
    if not cmd or not n:
        return list(cmd)
    name = Path(str(cmd[0])).name.lower().removesuffix(".exe")
    if name == "ffmpeg":
        return [cmd[0]] + ffmpeg_args(cmd[1:], n)
    if name == "ffprobe":
        return [cmd[0]] + ffprobe_args(cmd[1:], n)
    return list(cmd)


# ---------------------------------------------------------------------------------------------- PATH shim
SHIM_SH = """#!/bin/sh
# Reel Room CPU cap (engine/rrlimits.py): adds -threads to {name}, runs it under nice. Regenerated by install().
exec "{py}" -S -I "{mod}" {name} "$@"
"""


def real_tool(name: str) -> str:
    """The real ffmpeg / ffprobe (platform.json, then PATH without the shim dir)."""
    try:
        pf = json.loads((SHIM_DIR.parent / "platform.json").read_text())
    except (OSError, ValueError):
        pf = {}
    if pf.get(name) and Path(pf[name]).exists() and Path(pf[name]).parent != SHIM_DIR:
        return pf[name]
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if Path(p) != SHIM_DIR)
    return shutil.which(name, path=path) or name


def _shim_python() -> str:
    """One stable interpreter for the shim (the Reel Room venv), so processes never rewrite it back and forth."""
    venv = SHIM_DIR.parent / "venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def write_shims() -> Path | None:
    """~/.reel-room/shim/{ffmpeg,ffprobe} (POSIX only). Returns the shim dir, None on Windows."""
    if os.name == "nt":
        return None
    SHIM_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        p = SHIM_DIR / name
        body = SHIM_SH.format(name=name, py=_shim_python(), mod=Path(__file__).resolve())
        if not p.exists() or p.read_text() != body:
            tmp = p.with_suffix(".tmp")
            tmp.write_text(body)
            tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            os.replace(tmp, p)
    return SHIM_DIR


def shim_bin(name: str) -> str | None:
    """The shim path when the cap is on and the shim exists, else None."""
    p = SHIM_DIR / name
    return str(p) if max_threads() and p.exists() and os.name != "nt" else None


def env_for(n: int | None) -> dict:
    """Environment overrides that carry the budget into child processes."""
    out = {ENV: str(n) if n else "off"}
    if not n:
        return out
    out.update({k: str(n) for k in THREAD_ENVS})
    shim = write_shims()
    if shim:
        path = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and Path(p) != shim]
        out["PATH"] = os.pathsep.join([str(shim)] + path)
        out["RR_REAL_FFMPEG"], out["RR_REAL_FFPROBE"] = real_tool("ffmpeg"), real_tool("ffprobe")
    return out


def install(proj=None) -> int | None:
    """Export the budget into os.environ (idempotent). Returns the budget (None = uncapped)."""
    n = max_threads(proj)
    os.environ.update(env_for(n))
    return n


def _shim_main(argv: list) -> int:
    """Shim entry: rrlimits.py ffmpeg|ffprobe <args...> -> exec the real tool with thread args, under nice."""
    name, args = argv[0], argv[1:]
    real = os.environ.get("RR_REAL_" + name.upper()) or real_tool(name)
    n = ffmpeg_threads()
    cmd = wrap([real] + args, n) if n else [real] + args
    try:
        if os.getpriority(os.PRIO_PROCESS, 0) < NICE:
            os.setpriority(os.PRIO_PROCESS, 0, NICE)
    except (AttributeError, OSError):
        pass
    os.execv(real, cmd)
    return 127


# ---------------------------------------------------------------------------------------------- load monitor
class LoadMonitor:
    """Samples the 1-minute load average and the CPU (cores) used by this process tree every `every` seconds."""

    def __init__(self, every: float = 2.0):
        self.every, self.samples, self._stop = every, [], threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)

    def _tree_cores(self) -> float:
        import subprocess
        try:
            out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pcpu="], capture_output=True, text=True,
                                 timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return 0.0
        rows = [r.split() for r in out.splitlines() if len(r.split()) == 3]
        kids, cpu = {}, {}
        for pid, ppid, pc in rows:
            kids.setdefault(int(ppid), []).append(int(pid))
            cpu[int(pid)] = float(pc.replace(",", "."))
        todo, total = [os.getpid()], 0.0
        while todo:
            p = todo.pop()
            total += cpu.get(p, 0.0)
            todo += kids.get(p, [])
        return round(total / 100.0, 2)

    def _run(self):
        t0 = time.time()
        while not self._stop.is_set():
            self.samples.append((round(time.time() - t0, 1), round(os.getloadavg()[0], 2), self._tree_cores()))
            self._stop.wait(self.every)

    def summary(self) -> dict:
        if not self.samples:
            return {}
        loads, trees = [s[1] for s in self.samples], [s[2] for s in self.samples]
        return {"samples": len(self.samples), "every_s": self.every, "load1_peak": max(loads),
                "load1_start": loads[0], "load1_mean": round(sum(loads) / len(loads), 2),
                "tree_cores_peak": max(trees), "tree_cores_mean": round(sum(trees) / len(trees), 2),
                "cores": cores(), "budget": max_threads()}


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in ("ffmpeg", "ffprobe"):
    sys.exit(_shim_main(sys.argv[1:]))
