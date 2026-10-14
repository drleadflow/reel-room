#!/usr/bin/env python3
"""Plan to video: turn a typed plan (plan_fast.py) into the project's composition inputs, then optionally render.

  compile_plan.py <project> [--plan work/plan_fast.json] [--style <id>] [--draft] [--final] [--no-llm] [--workers 6]

  (no flag)  validate the plan, pick the style, resolve hero beats to a kit fallback (work/hero_todo.json), write
             edl.json shot fields (mode, top, punch) + project.json (style, motion, hook, beats, overlays, captions).
             The normal compose -> render -> deliver -> QA path then runs with no manual editing.
  --draft    then a fast preview render for approval (15 fps, draft encoder): renders/<slug>-<style>-draft.mp4
  --final    then render (high) -> deliver -> qa.py on the master (runs after --draft when both are given)
  --style    override the plan's styles (single-style reel). Supported: split-deck, motion-editorial, editorial-ui
             (editorial-ui also writes work/cutout_need.json for the cut-out, engine/pipeline.py runs it in parallel).
  --no-llm   hero fallbacks without a model call (the anchor word on a big card)
  --motion   calm (default: settle only + soft section transitions, density gates exempt) | polished
Prints a JSON report (timings in seconds). Exit 1 on a plan error (the message names the beat) or a failed QA.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from compile import hero_lib as HL  # noqa: E402
from compile import heroes as H  # noqa: E402
from compile import editorial_ui, motion_editorial, split_deck  # noqa: E402
from compile import split_engine as SE  # noqa: E402
from compile import validate as V  # noqa: E402
from compile.common import CompileError, jload, jwrite, load_inputs, no_dash, seg_words  # noqa: E402
from compile.kinds import classify  # noqa: E402

ADAPTERS = {"split-deck": split_deck, "motion-editorial": motion_editorial, "editorial-ui": editorial_ui}
NOT_YET = {
    "clean-talk": "overlay timeline (ct_headline / ct_type / ct_card / ct_lab spans across cuts), not per-segment tops",
    "list-stack": "one persistent list overlay built from the whole reel, plus hero payoff specs per item",
    "floating-cards": "stylekit project (template + style_cfg) and a cut-out matte for the behind-head word",
    "carousel-slideup": "stylekit project: one cream card per point with its own copy, no captions",
    "desk-demo": "stylekit project with phone-filmed screen recordings (assets the plan cannot invent)",
}
RUNNER = HERE / "compile" / "runner.py"
RUNNERS = {"editorial-ui": HERE / "compile" / "runner_eui.py"}     # styles with their own template build


def pick_style(plan: dict, override: str | None) -> str:
    if override:
        style = override
    else:
        styles = list(dict.fromkeys(s["style"] for s in plan.get("sections", [])))
        if len(styles) != 1:
            raise CompileError(
                f"the plan uses {len(styles)} styles ({', '.join(styles)}). Multi-style reels are not supported: "
                "each template composes the whole A-roll with its own captions, motion plan and sound pass, so "
                "sections cannot be stitched without seams. Pass --style <id> for a single-style reel.")
        style = styles[0]
    if style not in ADAPTERS:
        why = NOT_YET.get(style, "unknown style id")
        raise CompileError(f"style {style!r} has no compiler adapter yet ({why}). Supported: {', '.join(ADAPTERS)}")
    return style


def contexts_of(lines: dict) -> dict:
    ids = list(lines)
    return {lid: " ".join(lines[j] for j in ids[max(0, i - 1):i + 2] if j != lid) for i, lid in enumerate(ids)}


def hero_windows(win: dict, beats: list, max_rows: int = 3, max_secs: float = 6.0) -> dict:
    """Seconds a hero can use: its own line plus the caption-only lines just before it in the same section (the
    split adapters let a hero borrow them, compile/rich.py)."""
    out = {}
    for i, b in enumerate(beats):
        t0, t1 = win[b["id"]]
        j = i
        while (j - 1 > 0 and i - (j - 1) <= max_rows and beats[j - 1].get("component") in (None, "none")
               and not beats[j - 1].get("hero") and beats[j - 1].get("section") == b.get("section")
               and t1 - win[beats[j - 1]["id"]][0] <= max_secs):
            j -= 1
            t0 = win[beats[j]["id"]][0]
        out[b["id"]] = round(t1 - t0, 2)
    return out


def resolve_heroes(inp: dict, beats: list, style: str, use_llm: bool) -> tuple:
    """Hero beats -> beats carrying a validated library hero (hero_lib, hero_args) when one fits, else the validated
    kit fallback (hero flag kept either way)."""
    adapter = ADAPTERS[style]
    lines = V.edl_lines(inp["edl"])
    secs = hero_windows(inp["win"], beats)
    res = H.resolve(inp["proj"], beats, contexts_of(lines), style, adapter.HERO_COMPONENTS, use_llm, secs)
    out = []
    for b in beats:
        if not b.get("hero"):
            out.append(b)
            continue
        fb = res["fallbacks"][b["id"]]
        cand = {**b, "component": fb["component"], "on_screen_text": fb["on_screen_text"],
                "anchor_word": fb["anchor_word"]}
        if V.check_plain({**cand, "hero": False}, b["line"], contexts_of(lines)[b["id"]]):
            cand = {**b, **{k: v for k, v in H.offline_pick(b).items() if k != "source"}}
        lib = res["library"].get(b["id"]) or {}
        if lib.get("hero", "none") != "none":
            data = HL.data_for(inp["proj"], lib["hero"], inp, beats)
            cand = {**cand, "hero_lib": lib["hero"], "hero_args": {**lib.get("args", {}), **data}}
        out.append({**cand, "hero": True})
    return out, res


def shots_of(inp: dict, beats: list) -> list:
    return [(b["id"], classify(b, seg_words(inp["words"], inp["win"][b["id"]]))) for b in beats]


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def check_rows(rows: list) -> None:
    """Every string the compiler writes into a shot is dash-free (names the beat)."""
    for r in rows:
        for s in _strings(r.get("top")):
            no_dash(f"beat {r['id']}", s)


def notes_for(inp: dict, plan: dict, shots: list) -> list:
    notes = []
    first = next(iter(V.edl_lines(inp["edl"])), None)
    pick = (plan.get("hook") or {}).get("pick")
    opening = next((s.get("line_ids", []) for s in plan.get("sections", [])), [first])
    if pick and pick not in opening:
        notes.append(f"planner suggests opening on {pick}; reordering the cut needs a re-assemble (not done)")
    for sid, s in shots:
        if s.get("dropped"):
            notes.append(f"beat {sid}: {s['comp']} had no on-screen text, shown as caption only")
        elif s["kind"] != "none" and not s.get("anchor"):
            notes.append(f"beat {sid}: anchor word not in the words, the graphic lands on the cut")
    return notes


def title_until(inp: dict, rows: list, min_secs: float = 2.0) -> float:
    """The hook title holds to the first cut after min_secs, or until the next graphic takes the stage."""
    ends = sorted(t1 for _, t1 in inp["win"].values())
    end = next((t for t in ends if t >= min_secs), ends[-1])
    nxt = next((inp["win"][r["id"]][0] for r in rows[1:] if r.get("top")), end)
    return min(end, nxt) if nxt > 0.9 else end


def number_gate(proj: Path) -> dict:
    """Every on-screen number is verified (engine/numcheck.py ledger) or removed: numgate.scrub shows an unverified
    number words-only or drops its graphic (each change is a compile note), then the gate fails LOUDLY when one is
    still on screen, or when graphics carry numbers and numcheck.py never ran."""
    import numgate as NG
    has = (proj / NG.LEDGER).exists()
    notes = NG.scrub(proj) if has else []
    bad = [b for b in NG.unverified(proj) if has or not b["where"].startswith("captions")]
    if bad:
        fix = "" if has else " Run engine/numcheck.py <project> (pipeline.py does) before compile."
        raise CompileError(f"{len(bad)} unverified number(s) would be on screen: " + "; ".join(
            f"{b['where']} {b['text']!r}" for b in bad[:6]) + "." + fix)
    if notes:
        pj = jload(proj / "project.json", {})
        rec = pj.get("compiled") or {}
        pj["compiled"] = {**rec, "notes": list(rec.get("notes") or []) + notes}
        jwrite(proj / "project.json", pj)
    return {"numbers_gate": {"ledger": has, "changes": len(notes)}, "number_notes": notes}


def compile_project(proj: Path, plan_rel: str, style: str | None, use_llm: bool, motion: str = "calm") -> dict:
    t0 = time.time()
    inp = load_inputs(proj, plan_rel)
    plan = inp["plan"]
    V.check_plan(plan, inp["edl"])
    style = pick_style(plan, style)
    adapter = ADAPTERS[style]
    beats, hero_res = resolve_heroes(inp, plan["beats"], style, use_llm)
    shots = shots_of(inp, beats)
    lines = V.edl_lines(inp["edl"])
    if style == "editorial-ui":
        report = {"plan": plan_rel, "style": style, "motion": motion, "shots": dict(Counter(s["kind"] for _, s in shots)),
                  "heroes": hero_res["fallbacks"], "notes": notes_for(inp, plan, shots),
                  "library_heroes": {k: v.get("hero") for k, v in hero_res.get("library", {}).items()}}
        extra = adapter.compile_project(proj, inp, plan, shots, report)
        gate = number_gate(proj)
        extra = {**extra, **gate, "notes": extra.get("notes", []) + gate["number_notes"]}
        return {**report, **extra, "hero_secs": hero_res["secs"], "secs": round(time.time() - t0, 2)}
    rows, pbeats = adapter.rows_and_beats(shots, lines, plan.get("title", ""), wins=inp["win"])
    if style == "motion-editorial" and rows and rows[0]["mode"] == "full" and not rows[0].get("top"):
        rows[0] = {**rows[0], "mode": "card"}       # the hook title sits on the paper stage, not over the face
    rows = SE.punch_runs(rows)
    rows = SE.calm_talk(rows) if motion == "polished" else rows
    check_rows(rows)
    patch = adapter.project_patch(inp["pj"], plan, pbeats, **({"first_seg_end": title_until(inp, rows)}
                                                               if style == "motion-editorial" else {}))
    extra = getattr(adapter, "MOTION_EXTRA", {}) if motion == "calm" else {}
    patch = {**patch, "motion": {**SE.MOTION_PRESETS[motion], **extra}}
    report = {"plan": plan_rel, "style": style, "motion": motion, "shots": dict(Counter(s["kind"] for _, s in shots)),
              "punches": sum(1 for r in rows if r.get("punch")), "heroes": hero_res["fallbacks"],
              "library_heroes": {k: v.get("hero") for k, v in hero_res.get("library", {}).items()},
              "notes": notes_for(inp, plan, shots)}
    SE.write(proj, inp["edl"], rows, patch, report)
    gate = number_gate(proj)
    report = {**report, **gate, "notes": report["notes"] + gate["number_notes"]}
    return {**report, "hero_secs": hero_res["secs"], "secs": round(time.time() - t0, 2)}


def run_render(mode: str, proj: Path, style: str, workers: int) -> dict:
    args = [sys.executable, str(RUNNERS.get(style, RUNNER)), mode, str(proj), "--workers", str(workers), "--tag", style]
    p = subprocess.run(args, capture_output=True, text=True)
    last = (p.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        res = json.loads(last)
    except json.JSONDecodeError:
        res = {"ok": False}
    if p.returncode and not res.get("steps"):
        res["error"] = (p.stderr or p.stdout)[-1500:]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--plan", default="work/plan_fast.json")
    ap.add_argument("--style")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--motion", choices=sorted(SE.MOTION_PRESETS), default="calm")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    try:
        out = {"compile": compile_project(proj, a.plan, a.style, not a.no_llm, a.motion)}
    except CompileError as exc:
        print(f"compile_plan: {exc}", file=sys.stderr)
        return 1
    style = out["compile"]["style"]
    for mode in [m for m, on in (("draft", a.draft), ("final", a.final)) if on]:
        out[mode] = run_render(mode, proj, style, a.workers)
        if not out[mode].get("ok"):
            print(json.dumps(out, indent=1))
            return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
