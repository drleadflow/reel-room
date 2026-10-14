#!/usr/bin/env python3
"""Validate a hand-written plan (Claude writes it, no API key needed) and save it as work/plan_fast.json, the exact
shape plan_fast.py writes, so compile_plan.py / pipeline.py build from it unchanged.

  validate_plan.py <project> <plan.json> [--out work/plan_fast.json] [--json]

Input (lines come from <project>/edl.json; ids must match its segment ids):
  {"title": "on-screen hook title (max 40 chars, no em dash)",
   "hook_id": "<segment id that should open the reel>",
   "sections": [{"name": "short", "style": "split-deck", "purpose": "hook|promise|proof|explain|transition|cta",
                 "line_ids": ["<ids in order>"]}],
   "hero_moments": [{"line_id": "<id>", "anchor_word": "<word from that line>", "idea": "2 concrete sentences",
                     "library": "<hero library id, optional>",
                     "args": {<that hero's fields, optional: see references/kit.md / hero_schema.catalog_text()>}}],
   "beats": [{"id": "<id>", "component": "<kit component or none>", "on_screen_text": "max 28 chars, the speaker's
              own words and numbers only", "anchor_word": "<word from the line>", "why": "max 12 words"}]}
`beats` lists every segment that is NOT a hero moment. A hero with `library` AND `args` is checked against the hero's
typed contract (hero_schema) and saved as the compile's library pick (work/hero_todo.json), so the library hero is
drawn with no API key; without `args` the compiler uses its kit fallback (or asks a model when a key is set). Checks are the planner's own (plan_schema.check_reel_plan,
check_beat with neighbouring lines as context, invented()), then the compiler's (compile/validate.check_plan).
Every problem is printed with its id; fix them all and run again. Exit 0 = saved, 1 = problems.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_schema as PS  # noqa: E402


def load_lines(proj: Path) -> dict:
    edl = json.loads((proj / "edl.json").read_text())
    segs = edl if isinstance(edl, list) else edl.get("segments", [])
    return {s["id"]: s["line"].strip() for s in segs if s.get("id") and str(s.get("line", "")).strip()}


def contexts(lines: dict) -> dict:
    ids = list(lines)
    return {lid: " ".join(lines[j] for j in ids[max(0, i - 1):i + 2] if j != lid) for i, lid in enumerate(ids)}


def check(plan: dict, lines: dict) -> list:
    errs = []
    err = PS.check_reel_plan(plan, lines)
    if err:
        errs.append(err)
    heroes = {h.get("line_id") for h in plan.get("hero_moments") or [] if isinstance(h, dict)}
    given = {b.get("id"): b for b in plan.get("beats") or [] if isinstance(b, dict)}
    ctx = contexts(lines)
    for lid, line in lines.items():
        if lid in heroes:
            continue
        b = given.get(lid)
        if b is None:
            errs.append(f"beat {lid}: missing (every line that is not a hero needs a beat; use component 'none')")
            continue
        e = PS.check_beat(line, ctx[lid])(b)
        if e:
            errs.append(f"beat {lid}: {e}")
    for lid in given:
        if lid not in lines:
            errs.append(f"beat {lid}: not a segment id in edl.json")
    return errs


def to_plan_fast(plan: dict, lines: dict) -> dict:
    heroes = {h["line_id"]: h for h in plan["hero_moments"]}
    section_of = {lid: s for s in plan["sections"] for lid in s["line_ids"]}
    given = {b["id"]: b for b in plan.get("beats") or []}
    beats = []
    for lid, line in lines.items():
        sec = section_of[lid]
        base = {"id": lid, "line": line, "section": sec["name"], "style": sec["style"], "purpose": sec["purpose"]}
        if lid in heroes:
            h = heroes[lid]
            beats.append({**base, "hero": True, "component": "custom", "anchor_word": h["anchor_word"],
                          "visual_intent": h["idea"], "attempts": [],
                          **({"library": h["library"]} if h.get("library") else {})})
        else:
            d = given[lid]
            beats.append({**base, "hero": False, **{k: d.get(k, "") for k in ("component", "on_screen_text",
                          "anchor_word", "why")}, "unresolved": False, "attempts": []})
    hook = plan.get("hook_id")
    return {"title": plan["title"], "hook": {"claude": hook, "votes": {hook: 1}, "pick": hook, "agreement": 1.0},
            "sections": plan["sections"], "hero_moments": plan["hero_moments"], "beats": beats,
            "stats": {"source": "hand-written (validate_plan.py)", "calls": 0, "cost_usd": 0.0}}


HERO_STYLES = ("split-deck", "motion-editorial", "editorial-ui")


def hero_picks(proj: Path, plan: dict, lines: dict) -> tuple:
    """(errors, todo rows) for heroes that carry library + args: validated per style the compiler may use."""
    try:
        import hero_schema as HS
        from compile import hero_lib as HL
    except ImportError as e:
        return [f"hero library unavailable ({e})"], []
    sources, ctx, errs, rows = HL.sources_text(proj), contexts(lines), [], []
    for h in plan.get("hero_moments") or []:
        if not (h.get("library") and h.get("args")):
            continue
        lid, ok_styles = h["line_id"], []
        for style in HERO_STYLES:
            ids = HL.allowed(style, sources)
            if h["library"] in ids:
                err = HS.validator(ids, lines[lid], ctx[lid], sources)({"hero": h["library"], "args": h["args"]})
                if err:
                    errs.append(f"hero {lid} ({h['library']}): {err}")
                    break
                ok_styles.append(style)
                rows.append({"line_id": lid, "line": lines[lid], "anchor_word": h["anchor_word"], "idea": h["idea"],
                             "style": style, "status": "library",
                             "library": {"hero": h["library"], "args": h["args"], "why": "picked in the plan",
                                         "source": "claude", "by": "validate_plan.py"}})
        if not ok_styles and not errs:
            errs.append(f"hero {lid}: {h['library']!r} cannot be drawn by any compiled style here")
    return errs, rows


def save_picks(proj: Path, rows: list) -> None:
    todo_path = proj / "work" / "hero_todo.json"
    old = json.loads(todo_path.read_text()) if todo_path.exists() else []
    keys = {(r["line_id"], r["style"]) for r in rows}
    todo_path.write_text(json.dumps([t for t in old if (t.get("line_id"), t.get("style")) not in keys] + rows,
                                    indent=1))


def compiler_check(proj: Path, out: dict) -> list:
    try:
        from compile.validate import check_plan
        from compile.common import CompileError
    except ImportError as e:
        return [f"compiler check unavailable ({e})"]
    try:
        check_plan(out, json.loads((proj / "edl.json").read_text()))
    except CompileError as e:
        return [str(e)]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("plan")
    ap.add_argument("--out", default="work/plan_fast.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    plan_path = Path(a.plan).expanduser()
    plan_path = plan_path if plan_path.is_absolute() else proj / plan_path
    try:
        plan = json.loads(plan_path.read_text())
    except (OSError, ValueError) as e:
        errs, out = [f"cannot read {plan_path}: {e}"], None
    else:
        lines = load_lines(proj)
        errs = check(plan, lines)
        picks = []
        if not errs:
            herr, picks = hero_picks(proj, plan, lines)
            errs += herr
        out = None if errs else to_plan_fast(plan, lines)
        errs = errs or compiler_check(proj, out)
    if not errs:
        dest = proj / a.out
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=1))
        if picks:
            save_picks(proj, picks)
    if a.json:
        print(json.dumps({"ok": not errs, "errors": errs, "out": None if errs else str(proj / a.out)}))
    else:
        for i, e in enumerate(errs, 1):
            print(f"{i}. {e}")
        print(f"PLAN OK -> {proj / a.out}" if not errs else f"PLAN HAS {len(errs)} PROBLEM(S): fix and run again")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
