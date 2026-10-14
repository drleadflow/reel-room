"""`reel doctor`: check every dependency and key, print a plain fix (the exact command for this OS) for each failure.

  OK    the thing works
  FAIL  required and missing: Reel Room will not run until it is fixed (the line below says how)
  WARN  works, but something will be slow, small or off (fix suggested)
  OFF   an optional feature is off (what it adds and how to turn it on)
Ends with READY or BLOCKED. Also writes ~/.reel-room/platform.json, which the engine reads for tool paths.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import rr_assets as A
import rr_common as R

NODE_MIN = 22


class Report:
    def __init__(self, json_mode: bool):
        self.items, self.json = [], json_mode

    def add(self, level: str, name: str, detail: str = "", fix: str = ""):
        self.items.append({"level": level, "name": name, "detail": detail, "fix": fix})
        if not self.json:
            print(f"{level:5} {name:16} {detail}".rstrip())
            if fix and level != "OK":
                print(f"{'':5} {'':16} fix: {fix}")

    @property
    def blocked(self) -> bool:
        return any(i["level"] == "FAIL" for i in self.items)


def ver(cmd: list, timeout: int = 60) -> tuple:
    try:
        R.HOME.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(R.HOME))
        return (r.stdout + r.stderr).strip(), r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e), 1


def check_tools(rep: Report, pf: dict) -> None:
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        if p:
            out, _ = ver([p, "-version"])
            m = re.search(r"version (\S+)", out)
            pf[tool] = p
            rep.add("OK", tool, f"{p} ({m.group(1) if m else '?'})")
        else:
            rep.add("FAIL", tool, "not found on PATH", R.fix("ffmpeg"))
    node, npx = shutil.which("node"), A.npx()
    if not node:
        rep.add("FAIL", "node", f"not found (need {NODE_MIN}+)", R.fix("node"))
    else:
        out, _ = ver([node, "--version"])
        m = re.match(r"v(\d+)", out)
        major = int(m.group(1)) if m else 0
        pf.update(node=node, node_version=out)
        rep.add("OK" if major >= NODE_MIN else "FAIL", "node", f"{out} at {node}" if major >= NODE_MIN
                else f"{out} is too old, need {NODE_MIN}+", R.fix("node"))
    if npx:
        pf["npx"] = npx
        out, rc = ver([npx, "--yes", R.HF_PIN, "--version"], timeout=600)
        if rc == 0 and re.search(r"\d+\.\d+\.\d+", out):
            pf["hf"] = [npx, "--yes", R.HF_PIN]
            rep.add("OK", "hyperframes", f"{R.HF_PIN}")
            out, rc = ver([npx, "--yes", R.HF_PIN, "browser", "path"], timeout=120)
            path = out.strip().splitlines()[-1] if out.strip() else ""
            rep.add("OK" if rc == 0 and Path(path).exists() else "FAIL", "render-chrome",
                    path if rc == 0 else "headless Chrome for rendering is not downloaded",
                    f"npx --yes {R.HF_PIN} browser ensure")
        else:
            rep.add("FAIL", "hyperframes", f"npx {R.HF_PIN} did not run ({out.strip()[-120:]})",
                    f"check your internet, then: npx --yes {R.HF_PIN} --version")
    elif node:
        rep.add("FAIL", "npx", "not found (it ships with Node)", R.fix("node"))


def check_python(rep: Report, pf: dict) -> None:
    py = R.venv_python()
    if not py.exists():
        rep.add("FAIL", "python-venv", f"no venv at {R.VENV}", R.fix("install"))
        return
    imports = R.edition()["imports"]
    code = ("import importlib,sys\nbad=[]\nfor m in sys.argv[1:]:\n  try: importlib.import_module(m)\n"
            "  except Exception as e: bad.append(m+': '+str(e)[:80])\n"
            "import cv2\nif not hasattr(cv2,'CascadeClassifier'): bad.append('cv2: no CascadeClassifier')\n"
            "print('BAD:'+'|'.join(bad)); print('PY:%d.%d.%d'%sys.version_info[:3])")
    out, rc = ver([str(py), "-c", code, *imports], timeout=180)
    bad = next((ln[4:] for ln in out.splitlines() if ln.startswith("BAD:")), "unknown error: " + out[-200:])
    pyv = next((ln[3:] for ln in out.splitlines() if ln.startswith("PY:")), "?")
    pf.update(python=str(py), venv=str(R.VENV))
    rep.add("OK", "python-venv", f"{py} (Python {pyv})")
    rep.add("OK" if not bad else "FAIL", "python-packages", f"{len(imports)} imports resolve" if not bad else bad,
            R.fix("install"))


def check_assets(rep: Report) -> None:
    for m in R.WHISPER:
        rep.add("OK" if A.whisper_cached(m) else "FAIL", f"whisper-{m}", "cached" if A.whisper_cached(m)
                else "speech model not downloaded", R.fix("assets"))
    u = A.have_u2net()
    rep.add("OK" if u else "FAIL", "cutout-model", str(u) if u else "u2net_human_seg.onnx missing", R.fix("assets"))
    g = A.gsap_path()
    rep.add("OK" if g.exists() else "FAIL", "gsap", str(g) if g.exists() else "animation library not cached",
            R.fix("assets"))
    fonts = sorted(R.SK.glob("templates/*/fonts/*.woff2"))
    missing = [n for n in A.HERO_FONTS if not (A.font_cache() / n).exists()]
    ok = fonts and not missing
    rep.add("OK" if ok else "FAIL", "fonts", f"{len(fonts)} bundled (OFL), hero fonts cached" if ok else
            f"not in the font cache: {', '.join(missing) or 'bundled fonts'} (reels would fall back to a system font)",
            R.fix("assets"))


def check_skill(rep: Report) -> None:
    dest = Path.home() / ".claude" / "skills" / "reel"
    ok = (dest / "SKILL.md").exists() and (
        (dest / "SKILL.md").resolve() == (R.SK / "SKILL.md").resolve()
        or ((dest / "edition.json").exists()
            and (dest / "edition.json").read_text() == (R.SK / "edition.json").read_text()))
    rep.add("OK" if ok else "FAIL", "claude-skill", str(dest) if ok else f"/reel is not installed at {dest}",
            R.fix("skill"))


KEY_FEATURES = {
    "OPENROUTER_API_KEY": ("https://openrouter.ai/keys",
                           "fast planning (about 20 s instead of Claude writing the plan), model picks for every beat "
                           "and hero, the AI number check on top of the speech re-check"),
    "GEMINI_API_KEY": ("https://aistudio.google.com/apikey", "AI style scan ('learn a style from my reels'); "
                       "without it the scan is a basic pixel read"),
    "ZERNIO_API_KEY": ("https://zernio.link/emeka-ajufo", "automatic posting from Claude (engine/post.py); without it you post by "
                       "hand from the delivered files"),
}
FULL_ONLY = {"OPENROUTER_API_KEY": "the vision judge (taste QA) and analyze_refs"}


def check_keys(rep: Report) -> None:
    ed = R.edition()
    found = R.load_env()
    for k, need in ed["keys"].items():
        url, adds = KEY_FEATURES[k]
        adds = adds + (f", {FULL_ONLY[k]}" if ed["edition"] == "full" and k in FULL_ONLY else "")
        if k in found:
            rep.add("OK", k.split("_")[0].lower() + "-key", f"set ({'environment' if found[k] == 'environment' else '.env'})")
        else:
            lvl = "WARN" if need == "recommended" else "OFF"
            rep.add(lvl, k.split("_")[0].lower() + "-key", f"not set, {need}. Turns on: {adds}",
                    f"get a key at {url}, then put {k}=... in .env (copy .env.example to .env)")


def check_machine(rep: Report) -> None:
    pdir = R.projects_dir()
    gb = R.free_gb(pdir)
    rep.add("OK" if gb >= R.MIN_FREE_GB else "WARN", "disk", f"{gb:.0f} GB free at {pdir}" if gb >= R.MIN_FREE_GB
            else f"only {gb:.1f} GB free at {pdir} (a reel can use 2 to 5 GB while it renders)",
            "free up space or set projectsDir in ~/.reel-room/brand.json to a bigger drive")
    import os
    cap = os.environ.get("RR_MAX_THREADS") or str(R.default_threads())
    rep.add("OK", "cpu-cap", f"RR_MAX_THREADS={cap} of {os.cpu_count()} cores, one heavy job at a time, nice 10")
    b = R.HOME / "brand.json"
    rep.add("OK" if b.exists() else "WARN", "brand", str(b) if b.exists() else "no brand yet (defaults are used)",
            R.fix("setup"))


def main(argv=None) -> int:
    argv = argv or []
    rep = Report("--json" in argv)
    pf = {"os": R.OS, "edition": R.edition()["edition"]}
    R.sync_env()
    check_tools(rep, pf)
    check_python(rep, pf)
    if R.venv_python().exists():
        check_assets(rep)
    check_skill(rep)
    check_keys(rep)
    check_machine(rep)
    pf["ready"] = not rep.blocked
    R.HOME.mkdir(parents=True, exist_ok=True)
    (R.HOME / "cache").mkdir(exist_ok=True)
    (R.HOME / "platform.json").write_text(json.dumps(pf, indent=1))
    if rep.json:
        print(json.dumps({"ready": not rep.blocked, "checks": rep.items}))
    else:
        off = sum(1 for i in rep.items if i["level"] in ("OFF", "WARN"))
        print("BLOCKED: fix the FAIL lines above, then run doctor again" if rep.blocked
              else "READY" + (f" ({off} optional item{'s' if off != 1 else ''} above)" if off else "")
              + f"\nNext: record 20 to 60 s of you talking (vertical), then {R.reel_cmd()} demo your-clip.mov")
    return 1 if rep.blocked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
