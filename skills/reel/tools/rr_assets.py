"""`reel assets`: download everything the engine needs once, with progress and resume.

  Whisper small.en + medium.en (faster-whisper, Hugging Face cache)   about 0.5 GB + 1.5 GB
  u2net_human_seg.onnx (person cut-out, rembg release)                 176 MB -> ~/.u2net/
  GSAP (animation library, GreenSock standard licence)                 75 KB  -> ~/.reel-room/cache/
  HyperFrames (pinned) + its headless Chrome                           about 250 MB (npm + ~/.cache/hyperframes)
Each item is skipped when it is already in place. Safe to re-run; a broken download resumes where it stopped.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import rr_common as R


def fetch(url: str, dest: Path, size: int | None = None, label: str = "") -> bool:
    """HTTP download with resume (Range) and a one-line progress meter. Returns True when the file is complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (size is None or dest.stat().st_size == size):
        print(f"  {label or dest.name}: already here")
        return True
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(5):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={"User-Agent": "reel-room-installer",
                                                   **({"Range": f"bytes={have}-"} if have else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:
                    have = 0
                total = have + int(r.headers.get("Content-Length") or 0)
                t0, done = time.time(), have
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            mb = (done - have) / 1e6 / max(time.time() - t0, 0.01)
                            print(f"\r  {label or dest.name}: {done / 1e6:7.1f} / {total / 1e6:.1f} MB "
                                  f"({100 * done / total:5.1f}%, {mb:.1f} MB/s)", end="", flush=True)
            print()
            if size is None or part.stat().st_size == size:
                part.replace(dest)
                return True
            print(f"  size mismatch ({part.stat().st_size} != {size}), retrying")
        except OSError as e:
            print(f"\n  download interrupted ({e}); resuming in 3 s ...")
            time.sleep(3)
    return False


def u2net_paths() -> list:
    return [Path.home() / ".u2net" / "u2net_human_seg.onnx",
            Path.home() / ".cache" / "hyperframes" / "background-removal" / "models" / "u2net_human_seg.onnx"]


def have_u2net() -> Path | None:
    return next((p for p in u2net_paths() if p.exists() and p.stat().st_size == R.U2NET_SIZE), None)


def gsap_path() -> Path:
    return R.HOME / "cache" / f"gsap-{R.GSAP_VER}.min.js"


WHISPER_CODE = """
import sys
from faster_whisper.utils import download_model
name, fetch = sys.argv[1], sys.argv[2] == "1"
try:
    print(download_model(name, local_files_only=True)); sys.exit(0)
except Exception:
    if not fetch:
        sys.exit(3)
print(download_model(name))
"""


def whisper_cached(name: str) -> bool:
    py = R.venv_python()
    return py.exists() and subprocess.run([str(py), "-c", WHISPER_CODE, name, "0"], capture_output=True).returncode == 0


def whisper(name: str) -> bool:
    if whisper_cached(name):
        print(f"  whisper {name}: already here")
        return True
    print(f"  whisper {name}: downloading (Hugging Face shows progress; resumes if interrupted)")
    return subprocess.run([str(R.venv_python()), "-c", WHISPER_CODE, name, "1"]).returncode == 0


def npx() -> str | None:
    return shutil.which("npx.cmd" if R.IS_WIN else "npx") or shutil.which("npx")


def hyperframes() -> bool:
    n = npx()
    if not n:
        print("  hyperframes: npx not found (install Node first)")
        return False
    print(f"  hyperframes: fetching {R.HF_PIN} (npm cache) ...", flush=True)
    R.HOME.mkdir(parents=True, exist_ok=True)       # run npx from our own folder: a package.json or .npmrc higher up
    r = subprocess.run([n, "--yes", R.HF_PIN, "--version"], capture_output=True, text=True, timeout=600,
                       cwd=str(R.HOME))
    if r.returncode:
        print("  hyperframes: failed:", (r.stderr or r.stdout).strip()[-300:])
        return False
    print("  hyperframes:", r.stdout.strip().splitlines()[-1])
    print("  hyperframes: making sure its headless Chrome is downloaded ...", flush=True)
    r = subprocess.run([n, "--yes", R.HF_PIN, "browser", "ensure"], capture_output=True, text=True, timeout=1200,
                       cwd=str(R.HOME))
    print("  chrome:", "ready" if r.returncode == 0 else "failed: " + (r.stderr or r.stdout).strip()[-300:])
    return r.returncode == 0


HERO_FONTS = ["PlayfairDisplay.woff2", "PlayfairDisplay-Italic.woff2", "JetBrainsMono.woff2"]
GOOGLE_FONTS = ["Instrument Serif"]           # requested by templates at render time; fetched once, then offline


def font_cache() -> Path:
    return R.HOME / "cache" / "fonts"


FONT_CODE = """
import os, sys
sys.path.insert(0, sys.argv[1])
import theme
cache = sys.argv[2]
for fam in sys.argv[3:]:
    for italic in (False, True):
        dest = os.path.join(cache, theme._slug(fam) + ("-Italic" if italic else "") + ".woff2")
        if not os.path.exists(dest):
            print(fam, "italic" if italic else "", "ok" if theme._google_font(fam, dest, italic=italic) else "FAILED")
"""


def fonts() -> bool:
    """Seed the engine's font cache with the bundled OFL fonts (the hero library copies its serif and mono from
    there and would otherwise fall back silently), then fetch the Google Fonts the templates ask for."""
    cache = font_cache()
    cache.mkdir(parents=True, exist_ok=True)
    for f in sorted(R.SK.glob("templates/*/fonts/*.woff2")):
        if not (cache / f.name).exists():
            shutil.copyfile(f, cache / f.name)
    py = R.venv_python()
    if py.exists():
        subprocess.run([str(py), "-c", FONT_CODE, str(R.SK / "templates" / "split"), str(cache), *GOOGLE_FONTS],
                       timeout=120)
    missing = [n for n in HERO_FONTS if not (cache / n).exists()]
    print("  fonts:", "ready" if not missing else f"MISSING {missing}")
    return not missing


def main(argv=None) -> int:
    argv = argv or []
    t0, ok = time.time(), True
    print("Downloading what Reel Room needs (one time). Free disk now: %.0f GB" % R.free_gb(Path.home()))
    if "--no-models" not in argv:
        for m in R.WHISPER:
            ok &= whisper(m)
    if not have_u2net():
        ok &= fetch(R.U2NET_URL, u2net_paths()[0], R.U2NET_SIZE, "cut-out model u2net_human_seg")
    else:
        print("  cut-out model: already here")
    ok &= fetch(R.GSAP_URL, gsap_path(), None, f"GSAP {R.GSAP_VER}")
    ok &= fonts()
    if "--no-hf" not in argv:
        ok &= hyperframes()
    print(f"assets {'done' if ok else 'INCOMPLETE'} in {time.time() - t0:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
