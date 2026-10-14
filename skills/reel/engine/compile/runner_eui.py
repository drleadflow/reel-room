#!/usr/bin/env python3
"""Render runner for compiled editorial-ui projects (own process: the template's imports never mix with the engine's).

  runner_eui.py draft <project> [--workers 6]     compose (bake the set) -> lint -> 15 fps preview, no mix
                                                   -> renders/<slug>-editorial-ui-draft.mp4
  runner_eui.py final <project> [--workers 6] [--out <dir>]
        templates/editorial-ui/make.py steps with a worker cap: compose (bake, cached) -> lint -> render (high) ->
        voice + UI SFX master (-14 LUFS) -> loop, poster -> stylekit QA + set checks -> engine/qa.py on the master
Prints one JSON line: {ok, file, master, qa_pass, qa_failed, steps: {name: seconds}}. Exit 1 when anything fails.
Needs the cut-out masks for the set frames (cutout_cache.py run, or pipeline.py which runs it in parallel).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
EUI = os.path.join(os.path.dirname(ENGINE), "templates", "editorial-ui")
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]   # compile/heroes.py must not shadow kit/heroes
sys.path.insert(0, EUI)
import plan as _plan  # noqa: E402  (puts stylekit on sys.path)
import kit  # noqa: E402  (stylekit)
import skqa  # noqa: E402

_spec = importlib.util.spec_from_file_location("eui_make", os.path.join(EUI, "make.py"))
make = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make)
compose = make.compose
import render  # noqa: E402  (split template, on sys.path through stylekit)
sys.path.append(ENGINE)
import cutout_cache as CC  # noqa: E402

PY = sys.executable
DRAFT_FPS = 15
MASTER_PRESET = "medium"    # same 9.5 Mbps target as make.py's "slow", about 40 % faster (time budget)


def hf_render(project: str, rel: str, quality: str, workers: int, fps: int | None = None) -> float:
    """hyperframes render with render.py's capture flags plus a worker cap (shared machine), like runner.py."""
    t = time.time()
    render.prep_media(project)
    env = dict(os.environ, PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS="180000", PRODUCER_PLAYER_READY_TIMEOUT_MS="180000")
    args = render.HF + ["render", "-o", rel, "--quality", quality, "--sdr", "--experimental-fast-capture=false",
                        "--workers", str(workers)] + (["--fps", str(fps)] if fps else [])
    p = subprocess.run(args, cwd=project, capture_output=True, text=True, env=env)
    log = (p.stdout or "") + (p.stderr or "")
    with open(os.path.join(project, "renders", ".render.log"), "w") as f:
        f.write(log)
    if p.returncode != 0 or not os.path.exists(os.path.join(project, rel)):
        tail = [x for x in log.splitlines() if x.strip() and not render.NOISE.search(x)][-12:]
        raise SystemExit("render failed (renders/.render.log):\n" + "\n".join(tail))
    return round(time.time() - t, 1)


def _timed(steps: dict, name: str, fn, *a, **kw):
    t = time.time()
    out = fn(*a, **kw)
    steps[name] = round(time.time() - t, 1)
    return out


def _compose_lint(project: str, steps: dict) -> dict:
    meta = _timed(steps, "compose_bake", compose.compose, project, bake_layer=True)
    errs, _warns, findings = _timed(steps, "lint", kit.lint, project)
    if errs:
        raise SystemExit("lint errors:\n" + str(findings)[-1500:])
    return meta


def draft(project: str, workers: int) -> dict:
    steps = {}
    pj = kit.jload(os.path.join(project, "project.json"), {})
    rel = f"renders/{pj.get('slug') or os.path.basename(project)}-editorial-ui-draft.mp4"
    _compose_lint(project, steps)
    steps["render"] = hf_render(project, rel, "draft", workers, DRAFT_FPS)
    return {"ok": True, "file": os.path.join(project, rel), "steps": steps}


def _voice_only(project: str, demo: str, out: str) -> dict:
    """The voice-only deliverable from the full master's video (stream copy, same picture) and the voice stem the mix
    just wrote: one video encode per round instead of two (make.py encodes twice)."""
    from deliver import make_master     # engine/deliver.py (on sys.path through stylekit)
    muxed = out[:-4] + ".mux.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", demo, "-i", os.path.join(project, "work", "voice_stem.wav"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest", muxed],
                   check=True)
    try:
        return {"master": make_master(muxed, out)}
    finally:
        os.remove(muxed)


def _master(project: str, meta: dict, out: str, steps: dict) -> str:
    raw = os.path.join(project, "renders", "raw.mp4")
    voice = os.path.join(project, meta["voice_src"])
    demo = os.path.join(out, "demo.mp4")
    t = time.time()
    mix = kit.mix_and_master(project, raw, voice, meta["cues"], demo, meta["frames"], preset=MASTER_PRESET)
    dry = _voice_only(project, demo, os.path.join(out, "demo-voiceonly.mp4"))
    meta["mix"], meta["mix_voiceonly"] = mix, dry
    kit.jsave(os.path.join(project, "work", "meta.json"), meta)
    make.link_master(demo)
    make.link_master(os.path.join(out, "demo-voiceonly.mp4"))
    kit.make_loop(demo, os.path.join(out, "loop.mp4"), meta["loop"]["t0"], meta["loop"].get("dur", 6.0))
    kit.make_poster(demo, os.path.join(out, "poster.jpg"), meta["poster"]["t"])
    shutil.copyfile(os.path.join(project, "index.html"), os.path.join(out, "qa", "index.html"))
    steps["mix_master"] = round(time.time() - t, 1)
    return demo


def _qa(project: str, demo: str, out: str, steps: dict) -> tuple:
    """Template QA (stylekit skqa + set checks) and the engine's qa.py on the master, run side by side."""
    qa_dir = os.path.join(out, "qa")
    t = time.time()
    make.write_layout_boxes(project, kit.jload(os.path.join(project, "work", "meta.json")))
    master = demo[:-4] + "-master.mp4"
    eng = subprocess.Popen([PY, os.path.join(ENGINE, "qa.py"), project, master, "--json"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = skqa.run(project, demo, qa_dir)
    pl = _plan.Plan(project)
    set_ok = make.set_checks(pl, qa_dir)
    make.contact(pl, demo, os.path.join(qa_dir, "contact.jpg"))
    eng.wait()
    steps["qa"] = round(time.time() - t, 1)
    rep = kit.jload(os.path.join(project, "qa", "report.json"), {})
    failed = [c["name"] for c in rep.get("checks", []) if not c.get("pass") and not c.get("skipped")]
    failed += [f"template:{c['name']}" for c in res.get("checks", []) if not c.get("pass")]
    failed += [] if set_ok else ["template:set_checks"]
    return bool(rep.get("pass")) and res.get("pass") and set_ok, failed


def final(project: str, workers: int, out: str | None = None) -> dict:
    steps = {}
    out = out or os.path.join(project, "renders", "editorial-ui")
    os.makedirs(os.path.join(out, "qa"), exist_ok=True)
    meta = _compose_lint(project, steps)
    if CC.waiting():                    # never render next to the cut-out worker (shared machine)
        _timed(steps, "cutout_wait", CC.wait_done, project)
    steps["render"] = hf_render(project, "renders/raw.mp4", "high", workers)
    demo = _master(project, meta, out, steps)
    ok, failed = _qa(project, demo, out, steps)
    return {"ok": ok, "file": demo, "master": demo[:-4] + "-master.mp4", "qa_pass": ok, "qa_failed": failed,
            "out": out, "steps": steps}


def main(argv: list) -> int:
    if len(argv) < 2 or argv[0] not in ("draft", "final"):
        print(__doc__)
        return 2
    project = os.path.abspath(argv[1])
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 6
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workers = __import__("rrlimits").render_workers(workers, project)   # engine-wide CPU budget
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    res = draft(project, workers) if argv[0] == "draft" else final(project, workers, out)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
