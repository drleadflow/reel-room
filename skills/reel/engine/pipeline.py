#!/usr/bin/env python3
"""Plan to finished, QA'd reel in one run, with the cut-out in parallel.

  pipeline.py <project> --style <id> [--plan-fresh --brief "..."] [--plan work/plan_fast.json] [--draft]
              [--workers 6] [--no-llm] [--json]

  t=0      the cut-out worker starts the moment the A-roll exists (styles that need one: editorial-ui), in order,
           cached per A-roll (engine/cutout_cache.py); it never re-computes a frame when only the plan changes
  t=0      plan_fast.py (only with --plan-fresh), numcheck.py (every on-screen number re-checked against the audio,
           unverified ones blocked), then compile_plan.py, which writes work/cutout_need.json; the worker
           then skips every frame the plan does not put on the set or behind a hero
  join     wait for the needed masks (the render never runs next to the cut-out on a shared machine). --overlap
           starts the set bake at once, each span waiting for its own masks (measured slower: CPU contention)
  render   compile_plan's runner: final render -> master -> full QA (draft first with --draft)
Model calls need the keys in the environment (set them in .env or the environment). Prints a JSON report: steps in
seconds, plan_to_qa_total, the cut-out numbers and the QA result. Exit 1 on a failed step or QA.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import rrlimits as RL  # noqa: E402  engine-wide CPU budget (RR_MAX_THREADS / project.json machine.max_threads)

PY = sys.executable
NICE = [] if os.name == "nt" else ["nice", "-n", "10"]     # same rule as common.nice_prefix (no nice on Windows)
NEEDS_CUTOUT = {"editorial-ui"}
RUNNERS = {"editorial-ui": HERE / "compile" / "runner_eui.py"}


def _run(args: list, label: str) -> tuple:
    t = time.time()
    p = subprocess.run(NICE + args, capture_output=True, text=True)
    return round(time.time() - t, 1), p


def _last_json(text: str) -> dict:
    for line in reversed((text or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def start_cutout(proj: Path):
    """The cut-out worker in follow mode (a stale need file from an older plan is moved aside first)."""
    need = proj / "work" / "cutout_need.json"
    if need.exists():
        os.replace(need, need.with_suffix(".prev.json"))
    (proj / "work" / "cutout.status.json").write_text(json.dumps({"state": "running", "engine": "cache"}))
    log = open(proj / "work" / "cutout.log", "w")
    args = NICE + [PY, str(HERE / "cutout_cache.py"), "run", str(proj), "--follow", "--need", str(need)]
    return subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT), time.time()


def join_cutout(proc, t_start: float, proj: Path) -> dict:
    t = time.time()
    code = proc.wait()
    status = json.loads((proj / "work" / "cutout.status.json").read_text()) \
        if (proj / "work" / "cutout.status.json").exists() else {}
    if code:
        raise SystemExit(f"cut-out failed ({code}): see {proj / 'work' / 'cutout.log'}")
    return {"cutout_secs": status.get("seconds"), "cutout_frames_computed": status.get("computed"),
            "cutout_frames_needed": status.get("needed"), "joined_after_secs": round(time.time() - t_start, 1)}


def _has_key() -> bool:
    import llm_router as LR
    try:
        return bool(LR.api_key())
    except LR.LLMError:
        return False


def plan_and_compile(a, proj: Path, steps: dict) -> dict:
    if a.plan_fresh:
        steps["plan_fast"], p = _run([PY, str(HERE / "plan_fast.py"), str(proj), "--brief", a.brief or "",
                                      "--out", a.plan], "plan_fast")
        if p.returncode:
            raise SystemExit("plan_fast failed:\n" + (p.stderr or p.stdout)[-1500:])
    no_llm = a.no_llm = a.no_llm or not _has_key()     # no key: speech-only numcheck, offline hero picks
    steps["numcheck"], p = _run([PY, str(HERE / "numcheck.py"), str(proj), "--json"] + (["--no-llm"] if no_llm else []),
                                "numcheck")
    if p.returncode:                    # every on-screen number checked against the audio before compile
        raise SystemExit("numcheck failed:\n" + (p.stderr or p.stdout)[-1500:])
    a.numbers = _last_json(p.stdout)
    cmd = [PY, str(HERE / "compile_plan.py"), str(proj), "--plan", a.plan, "--style", a.style]
    steps["compile"], p = _run(cmd + (["--no-llm"] if a.no_llm else []), "compile")
    if p.returncode:
        raise SystemExit("compile failed:\n" + p.stderr[-2000:])
    return json.loads(p.stdout)["compile"]


def render(a, proj: Path, steps: dict, overlap: bool = False) -> dict:
    """overlap: the cut-out is still running; the runner's bake waits per span for its masks and the render waits
    for the worker to finish (REEL_CUTOUT_WAIT), so the bake overlaps the cut-out and the render never does."""
    runner = str(RUNNERS.get(a.style, HERE / "compile" / "runner.py"))
    if overlap:
        os.environ["REEL_CUTOUT_WAIT"] = "1"
    out = {}
    if a.draft:
        steps["draft_render"], p = _run([PY, runner, "draft", str(proj), "--tag", a.style, "--workers",
                                         str(a.workers)], "draft")
        out["draft"] = _last_json(p.stdout)
    steps["final_total"], p = _run([PY, runner, "final", str(proj), "--tag", a.style, "--workers",
                                    str(a.workers)], "final")
    final = _last_json(p.stdout)
    if not final:
        raise SystemExit("final render failed:\n" + (p.stderr or p.stdout)[-2000:])
    for k, v in (final.get("steps") or {}).items():
        steps[f"final_{k}"] = v
    return {**out, "final": final}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--style", required=True)
    ap.add_argument("--plan", default="work/plan_fast.json")
    ap.add_argument("--plan-fresh", action="store_true")
    ap.add_argument("--brief")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--overlap", action="store_true", help="bake while the cut-out runs (slower on a loaded machine)")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    rep = {"budget": {"max_threads": RL.install(proj), "cores": RL.cores()}}    # children inherit the cap
    a.workers = RL.render_workers(a.workers, proj)
    with RL.LoadMonitor() as mon:
        run_all(a, proj, rep)
    rep["load"] = mon.summary()
    print(json.dumps(rep, indent=1))
    return 0 if rep["final"].get("qa_pass") else 1


def run_all(a, proj: Path, rep: dict) -> None:
    t0, steps = time.time(), {}
    worker = start_cutout(proj) if a.style in NEEDS_CUTOUT else None
    rep["compile"] = plan_and_compile(a, proj, steps)
    rep["numbers"] = getattr(a, "numbers", {})
    if worker:          # measured: baking next to the cut-out starves both (bake 153 s, cut-out 4.5 fps), so join first
        t = time.time()
        rep["cutout"] = join_cutout(*worker, proj)
        steps["cutout_join_wait"] = round(time.time() - t, 1)
    rep.update(render(a, proj, steps, overlap=a.overlap))
    steps["plan_to_qa_total"] = round(time.time() - t0, 1)
    rep["steps_secs"] = steps


if __name__ == "__main__":
    sys.exit(main())
