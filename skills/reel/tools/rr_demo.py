"""`reel demo <your clip>`: turn one clip of you talking into a finished reel, end to end, in a few minutes.

  reel demo my-clip.mov [--style split-deck|editorial-ui] [--fresh-plan] [--no-open] [--into <folder>] [--force]

Record 20 to 60 seconds of yourself talking about one idea, phone held upright (vertical), any phone is fine.
Steps (the same engine commands /reel runs):
  check the clip (vertical, 15 to 120 s, has sound, one face) -> ingest (transcript) -> a first-pass edit from your
  own words (pauses and repeated takes cut, tools/rr_autoedit.py) -> splice words / snap (cuts land in real silence)
  -> assemble -> face position -> captions -> plan from your words, checked by validate_plan.py (no API key needed;
  --fresh-plan asks the fast planner instead, needs OPENROUTER_API_KEY) -> compile -> number check -> render ->
  deliver -> QA on the master.
For the full treatment (best takes picked by ear, a plan written for your reel, notes and rounds) use /reel in Claude
Code with the same clip.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import rr_common as R

DEMO_STYLES = ["split-deck", "editorial-ui"]          # the styles the demo is tested on
MIN_S, MAX_S = 15, 120
HOWTO = """Record a 20 to 60 second vertical video of yourself talking about one idea, any phone is fine, then run:
  {cmd} demo your-clip.mov

Step by step:
  1. Hold the phone upright, face the camera, keep talking through mistakes (just say the line again).
  2. Copy it to this computer, then run:

       {cmd} demo your-clip.mov

     (drag the file into the terminal to paste its path)
  3. A few minutes later you get the finished reel, captions file, cover and a share copy.
"""


def probe(clip: Path) -> dict:
    ff = shutil.which("ffprobe")
    if not ff:
        raise SystemExit(f"ffprobe is missing. Fix: {R.fix('ffmpeg')}")
    r = subprocess.run([ff, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(clip)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"I can't read {clip.name} as a video. Export it from your phone as .mov or .mp4 and try again.")
    j = json.loads(r.stdout or "{}")
    v = next((x for x in j.get("streams", []) if x.get("codec_type") == "video"), None)
    if not v:
        raise SystemExit(f"{clip.name} has no picture. Use a video file (.mov or .mp4).")
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    rot = abs(int(float((v.get("tags") or {}).get("rotate", rot)))) % 360
    w, h = int(v["width"]), int(v["height"])
    if rot in (90, 270):
        w, h = h, w
    return {"w": w, "h": h, "dur": float(j.get("format", {}).get("duration") or v.get("duration") or 0),
            "audio": any(x.get("codec_type") == "audio" for x in j.get("streams", []))}


def faces(clip: Path, dur: float) -> list:
    """faces found in 8 frames spread over the clip (Haar, the engine's own detector)"""
    try:
        import cv2
    except ImportError:
        return []
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out = []
    for k in range(8):
        t = dur * (k + 0.5) / 8
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-vf",
                            "scale=540:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        import numpy as np
        img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_GRAYSCALE) if r.stdout else None
        out.append(0 if img is None else len(casc.detectMultiScale(img, 1.1, 5, minSize=(50, 50))))
    return out


def check_clip(clip: Path, force: bool) -> dict:
    """plain-language checks before any heavy work"""
    if not clip.exists():
        raise SystemExit(f"I can't find {clip}. Drag the file into the terminal to paste its exact path.")
    p = probe(clip)
    problems = []
    if p["h"] <= p["w"]:
        problems.append(f"it is horizontal ({p['w']}x{p['h']}). Reels are vertical: hold the phone upright and "
                        "record again")
    if p["dur"] < MIN_S:
        problems.append(f"it is {p['dur']:.0f} s long. Talk for at least {MIN_S} s (20 to 60 s is ideal)")
    if p["dur"] > MAX_S:
        problems.append(f"it is {p['dur']:.0f} s long. Keep the demo under {MAX_S} s (trim it, or use /reel in "
                        "Claude Code for longer videos)")
    if not p["audio"]:
        problems.append("it has no sound. The edit follows your words, so record with the microphone on")
    if not problems:
        f = faces(clip, p["dur"])
        seen = sum(1 for n in f if n >= 1)
        many = sum(1 for n in f if n >= 2)
        if f and seen < len(f) // 2:
            problems.append("I can't see a face in most of it. Face the camera, with your face well lit and in frame")
        elif f and many > len(f) // 2:
            problems.append("I see more than one face. The demo is made for one person talking to camera")
    if problems:
        msg = f"This clip won't make a good demo reel yet: " + "; ".join(problems) + "."
        if not force:
            raise SystemExit(msg + "\n(Add --force to try anyway.)")
        print("WARNING: " + msg + " Continuing because of --force.")
    return p


def step(name: str, cmd: list, times: dict, check: bool = True) -> subprocess.CompletedProcess:
    t = time.time()
    print(f"  {name} ...", end="", flush=True)
    p = subprocess.run(R.nice_prefix() + [str(c) for c in cmd], capture_output=True, text=True)
    times[name] = round(time.time() - t, 1)
    print(f" {times[name]} s" + ("" if p.returncode == 0 else "  FAILED" if check else ""))
    if p.returncode and (check or "\n{" not in "\n" + p.stdout):
        tail = "\n".join(((p.stderr or "") + (p.stdout or "")).strip().splitlines()[-25:])
        raise SystemExit(f"\n{name} failed:\n{tail}\n\nRun `{R.reel_cmd()} doctor` and fix any FAIL line first.")
    return p


def missing_fonts(proj: Path) -> list:
    """every font file a composition asks for (@font-face url) that is not on disk: the browser would silently
    fall back to a system font and the reel would look off-brand"""
    import re
    miss = []
    for html in [proj / "index.html", *sorted((proj / "compositions").glob("**/*.html"))]:
        if html.exists():
            for rel in re.findall(r"url\(['\"]?(assets/fonts/[^'\")]+)", html.read_text(errors="ignore")):
                if not (proj / rel).exists() and rel not in miss:
                    miss.append(rel)
    return miss


def qa_details(proj: Path, final: dict) -> list:
    """one plain line per failed check, from the engine QA and (editorial-ui) the template QA reports"""
    out, reports = [], [proj / "qa" / "report.json"]
    if final.get("out"):
        reports += [Path(final["out"]) / "qa" / "report.json", Path(final["out"]) / "qa" / "set_report.json"]
    for r in reports:
        try:
            rep = json.loads(r.read_text())
        except (OSError, ValueError):
            continue
        for c in rep.get("checks", []):
            if not c.get("pass") and not c.get("skipped"):
                d = c.get("detail")
                out.append(f"  - {c.get('name')}: {d if isinstance(d, str) else json.dumps(d)[:300]}")
    return out


def open_folder(path: Path) -> None:
    opener = {"mac": ["open"], "windows": ["explorer"], "linux": ["xdg-open"]}[R.OS]
    if shutil.which(opener[0]):
        subprocess.run(opener + [str(path)], capture_output=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reel demo", description=__doc__.split("\n")[0])
    styles = R.edition()["styles"]
    ap.add_argument("clip", nargs="?", help="your video: 20 to 60 s, vertical, you talking to camera")
    ap.add_argument("--style", default="split-deck", choices=[s for s in DEMO_STYLES if s in styles])
    ap.add_argument("--fresh-plan", action="store_true", help="plan with the fast planner (needs OPENROUTER_API_KEY)")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--force", action="store_true", help="skip the clip checks")
    ap.add_argument("--into", help="parent folder for the demo project (default: projectsDir from brand.json)")
    a = ap.parse_args(argv)
    if not a.clip:
        print(HOWTO.format(cmd=R.reel_cmd()))
        return 0
    keys = R.load_env()
    if a.fresh_plan and "OPENROUTER_API_KEY" not in keys:
        raise SystemExit("--fresh-plan needs OPENROUTER_API_KEY in .env (or drop the flag: the demo plans without it)")
    py, eng = R.venv_python(), R.SK / "engine"
    if not py.exists():
        raise SystemExit(f"Not installed yet. Run: {R.fix('install')}")
    clip = Path(a.clip).expanduser().resolve()
    info = check_clip(clip, a.force)
    parent = Path(a.into).expanduser() if a.into else R.projects_dir()
    parent.mkdir(parents=True, exist_ok=True)
    if R.free_gb(parent) < R.MIN_FREE_GB:
        print(f"WARNING: only {R.free_gb(parent):.1f} GB free at {parent}. A reel can need 2 to 5 GB while it renders.")
    sys.path.insert(0, str(eng))
    import rr_autoedit as AE
    proj = parent / f"demo-{a.style}-{time.strftime('%Y%m%d-%H%M%S')}"
    times, t0 = {}, time.time()
    with R.HeavyLock(f"reel demo {a.style}"):
        proj.mkdir()
        print(f"Reel Room demo ({a.style}): {clip.name}, {info['dur']:.0f} s -> {proj}\n  machine: "
              f"{R.machine_line()}, RR_MAX_THREADS={os.environ.get('RR_MAX_THREADS') or R.default_threads()}")
        step("ingest", [py, eng / "ingest.py", proj, clip], times)
        (proj / "work").mkdir(exist_ok=True)
        edl, plan = AE.write(proj, a.style)
        title = plan["title"].title()
        (proj / "project.json").write_text(json.dumps(
            {"slug": "demo", "title": title, "style": a.style, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "hook": {"l1": plan["title"], "l2": "", "category": "Promise"},
             "motion": {"level": "polished", "sfx": "light"}}, indent=1))
        print(f"  first-pass edit: {len(edl)} phrases kept, title \"{plan['title']}\"")
        step("splice words", [py, eng / "splice.py", proj, "words"], times)
        step("splice snap", [py, eng / "splice.py", proj, "snap"], times)
        step("assemble", [py, eng / "assemble.py", proj], times)
        step("face position", [py, eng / "headpos.py", proj], times)
        step("captions", [py, eng / "words.py", proj, "build"], times)
        if a.fresh_plan:
            step("plan (fast planner)", [py, eng / "plan_fast.py", proj, "--brief",
                                         "Instagram reel from a talking-head clip. Clear, premium, easy to follow."],
                 times)
        else:
            step("plan (from your words, validated)", [py, eng / "validate_plan.py", proj, "work/plan_draft.json"],
                 times)
        cmd = [py, eng / "pipeline.py", proj, "--style", a.style]
        if "OPENROUTER_API_KEY" not in keys:
            cmd.append("--no-llm")
        p = step("render + QA", cmd, times, check=False)     # a QA miss still delivers files: report it below
    out = "\n" + p.stdout
    try:
        rep = json.loads(out[out.rindex("\n{"):])
    except ValueError:
        rep = {}
    final = rep.get("final") or {}
    total = round(time.time() - t0)
    failed = list(final.get("qa_failed") or [])
    qa_ok = bool(final.get("qa_pass"))
    fonts_missing = missing_fonts(proj)
    if fonts_missing:
        print(f"\nFONT CHECK FAILED: the reel asked for fonts that are not installed: {', '.join(fonts_missing)}."
              f" Run `{R.reel_cmd()} assets`, then the demo again.")
    (proj / "demo_timing.json").write_text(json.dumps({"steps_secs": times, "total_secs": total, "style": a.style,
                                                       "clip_secs": round(info["dur"], 1),
                                                       "machine": R.machine_line()}, indent=1))
    print(f"\nDone in {total // 60} min {total % 60} s. QA {'passed' if qa_ok else 'flagged ' + str(len(failed))}"
          + ("" if qa_ok else " check(s): the files are delivered, here is what to look at:"))
    if not qa_ok:
        print("\n".join(qa_details(proj, final)) + f"\n  (full reports: {proj / 'qa'}; /reel in Claude Code fixes "
              "these for you)")
    print(f"Your reel: {final.get('master') or proj / 'renders'}")
    print(f"Everything else (share copy, silent version, captions .srt, cover): {proj / 'renders'}")
    if qa_ok and not fonts_missing:
        other = next((x for x in DEMO_STYLES if x != a.style), None)
        if other:
            print(f"Try another style: {R.reel_cmd()} demo \"{clip}\" --style {other}")
    if not a.no_open:
        open_folder(proj / "renders")
    return 0 if qa_ok and not fonts_missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
