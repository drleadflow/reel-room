"""Shared helpers for the `reel` command: paths, edition info, keys, OS fixes, the one-heavy-job lock.
Pure stdlib, runs on any Python 3.9+ (the installer calls it before the venv exists)."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

SK = Path(__file__).resolve().parents[1]                  # skills/reel
REPO = SK.parents[1] if (SK.parents[1] / "install.sh").exists() else None
HOME = Path(os.environ.get("REEL_ROOM_HOME") or Path.home() / ".reel-room")
VENV = HOME / "venv"
IS_WIN = os.name == "nt"
OS = {"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux")
HF_PIN = "hyperframes@0.8.34"
GSAP_VER = "3.14.2"
GSAP_URL = f"https://cdn.jsdelivr.net/npm/gsap@{GSAP_VER}/dist/gsap.min.js"
U2NET_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
U2NET_SIZE = 175997641
WHISPER = ["small.en", "medium.en"]
MIN_FREE_GB = 10


def edition() -> dict:
    return json.loads((SK / "edition.json").read_text())


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")


def install_info() -> dict:
    p = HOME / "install.json"
    return json.loads(p.read_text()) if p.exists() else {}


def repo_dir() -> Path | None:
    if REPO:
        return REPO
    r = install_info().get("repo")
    return Path(r) if r and Path(r).exists() else None


# ------------------------------------------------------------------------- keys (.env or environment only)
def read_env_file(p: Path) -> dict:
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:
                out[k.strip()] = v
    return out


def env_files() -> list:
    files = [HOME / ".env"]
    r = repo_dir()
    if r:
        files.insert(0, r / ".env")
    return files


def load_env() -> dict:
    """Keys from the environment first, then <repo>/.env, then ~/.reel-room/.env. Puts them into os.environ so
    every engine step inherits them. Returns {name: source} (never the values)."""
    seen = {}
    for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "ZERNIO_API_KEY"):
        if os.environ.get(k, "").strip():
            seen[k] = "environment"
    for f in env_files():
        for k, v in read_env_file(f).items():
            if k not in os.environ or not os.environ[k].strip():
                os.environ[k] = v
                seen.setdefault(k, str(f))
    return seen


def sync_env() -> None:
    """The engine reads ~/.reel-room/.env. Keep it pointing at the repo .env (symlink; a copy on Windows)."""
    r = repo_dir()
    if not r or not (r / ".env").exists():
        return
    HOME.mkdir(parents=True, exist_ok=True)
    dest, src = HOME / ".env", r / ".env"
    if dest.is_symlink() or not dest.exists():
        if dest.is_symlink() and dest.resolve() == src.resolve():
            return
        try:
            if dest.is_symlink():
                dest.unlink()
            dest.symlink_to(src)
            return
        except OSError:
            pass
    if not dest.is_symlink() and (not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime):
        shutil.copyfile(src, dest)


# ------------------------------------------------------------------------- per-OS fixes
INSTALL = {"mac": "./install.sh", "linux": "./install.sh",
           "windows": "powershell -ExecutionPolicy Bypass -File .\\install.ps1"}
FIX = {
    "python": {"mac": "brew install python@3.12", "linux": "sudo apt-get install -y python3.12 python3.12-venv",
               "windows": "winget install -e --id Python.Python.3.12"},
    "ffmpeg": {"mac": "brew install ffmpeg", "linux": "sudo apt-get install -y ffmpeg",
               "windows": "winget install -e --id Gyan.FFmpeg   (then open a new terminal)"},
    "node": {"mac": "brew install node@22 && brew link --overwrite --force node@22",
             "linux": "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs",
             "windows": "winget install -e --id OpenJS.NodeJS.LTS   (then open a new terminal)"},
}


def fix(what: str) -> str:
    if what in FIX:
        return FIX[what][OS]
    return {"install": INSTALL[OS], "assets": f"{reel_cmd()} assets", "setup": f"{reel_cmd()} setup",
            "skill": INSTALL[OS] + " --skill-only"}.get(what, what)


def reel_cmd() -> str:
    return ".\\reel.cmd" if IS_WIN else "./reel"


# ------------------------------------------------------------------------- machine
def free_gb(path: Path) -> float:
    p = Path(path)
    while not p.exists():
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def default_threads() -> int:
    return max(2, (os.cpu_count() or 4) // 2)


def brand() -> dict:
    p = HOME / "brand.json"
    return json.loads(p.read_text()) if p.exists() else json.loads((SK / "brand.default.json").read_text())


def projects_dir() -> Path:
    return Path(os.path.expanduser(brand().get("projectsDir") or "~/ReelRoom"))


class HeavyLock:
    """One heavy job (render, cut-out, transcription) at a time on this machine."""

    def __init__(self, label: str):
        self.path, self.label, self.fh = HOME / "heavy.lock", label, None

    def __enter__(self):
        HOME.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            if IS_WIN:
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.seek(0)
            who = self.fh.read().strip() or "another reel job"
            raise SystemExit(f"Another heavy Reel Room job is running ({who}). Wait for it to finish, then try again.")
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(f"{self.label} pid {os.getpid()} since {time.strftime('%H:%M:%S')}")
        self.fh.flush()
        return self

    def __exit__(self, *a):
        try:
            self.fh.seek(0)
            self.fh.truncate()
            self.fh.close()
        except OSError:
            pass


def nice_prefix() -> list:
    return [] if IS_WIN or not shutil.which("nice") else ["nice", "-n", "10"]


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], **kw)


def machine_line() -> str:
    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} cores"
