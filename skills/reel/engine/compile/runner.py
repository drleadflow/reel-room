#!/usr/bin/env python3
"""Render runner for compiled projects (run as its own process, like templates/split/render.py, so the split engine's
imports never mix with the engine's).

  runner.py draft <project> [--tag <name>] [--workers 6]   compose -> lint -> fast preview (15 fps, draft encoder,
                                                            capped workers) -> SFX mix -> renders/<slug>-<tag>-draft.mp4
  runner.py final <project> [--workers 6]                  compose -> lint -> render (high) -> SFX mix -> deliver.py
                                                            -> qa.py on the master (full QA incl. motion gates)
Prints one JSON line: {ok, file, steps: {name: seconds}, ...}. Exit 1 when lint, render or QA fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
SPLIT = os.path.join(os.path.dirname(ENGINE), "templates", "split")
sys.path.insert(0, SPLIT)
import compose  # noqa: E402
import render  # noqa: E402

DRAFT_FPS = 15
PY = sys.executable


def hf_render(project: str, rel: str, quality: str, workers: int, fps: int | None = None) -> float:
    """hyperframes render with the same capture flags as render.py plus a worker cap (shared machine)."""
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


def compose_lint(project: str) -> float:
    t = time.time()
    compose.compose(project, overlay=False)
    errs, warns, out = render.lint(project)
    if errs:
        raise SystemExit("lint errors:\n" + render.short_findings(out, "error"))
    return round(time.time() - t, 1)


def mix_sfx(project: str, pj: dict, rel: str) -> float:
    t = time.time()
    if (pj.get("sound") or {}).get("cues") or render.motion_sfx_on(project, pj):
        import soundcues
        soundcues.apply(project, rel)
    return round(time.time() - t, 1)


def _pj(project: str) -> dict:
    p = os.path.join(project, "project.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def draft(project: str, tag: str, workers: int) -> dict:
    pj = _pj(project)
    slug = pj.get("slug") or os.path.basename(project)
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    rel = f"renders/{slug}-{tag}-draft.mp4"
    steps = {"compose_lint": compose_lint(project)}
    steps["render"] = hf_render(project, rel, "draft", workers, DRAFT_FPS)
    steps["sfx_mix"] = mix_sfx(project, pj, rel)
    return {"ok": True, "file": os.path.join(project, rel), "steps": steps}


def _run_json(args: list) -> tuple:
    t = time.time()
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr, round(time.time() - t, 1)


def final(project: str, workers: int) -> dict:
    pj = _pj(project)
    slug = pj.get("slug") or os.path.basename(project)
    rel = f"renders/{slug}-v{render.next_version(project, slug)}.mp4"
    steps = {"compose_lint": compose_lint(project)}
    steps["render"] = hf_render(project, rel, "high", workers)
    steps["sfx_mix"] = mix_sfx(project, pj, rel)
    src = os.path.join(project, rel)
    code, out, err, steps["deliver"] = _run_json([PY, os.path.join(ENGINE, "deliver.py"), project, src])
    if code:
        raise SystemExit("deliver failed:\n" + err[-1200:])
    master = src[:-4] + "-master.mp4"
    code, out, err, steps["qa"] = _run_json([PY, os.path.join(ENGINE, "qa.py"), project, master, "--json"])
    rep = json.load(open(os.path.join(project, "qa", "report.json")))
    failed = [c["name"] for c in rep.get("checks", []) if not c.get("pass") and not c.get("skipped")]
    return {"ok": bool(rep.get("pass")), "file": src, "master": master, "qa_pass": bool(rep.get("pass")),
            "qa_failed": failed, "steps": steps}


def main(argv: list) -> int:
    if len(argv) < 2 or argv[0] not in ("draft", "final"):
        print(__doc__)
        return 2
    project = os.path.abspath(argv[1])
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 6
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workers = __import__("rrlimits").render_workers(workers, project)   # engine-wide CPU budget
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "plan"
    res = draft(project, tag, workers) if argv[0] == "draft" else final(project, workers)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
