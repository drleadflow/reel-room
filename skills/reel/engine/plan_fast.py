#!/usr/bin/env python3
"""Fast planner: one creative pass for the whole reel, then typed per-beat decisions in parallel.

  Stage A (Claude, one call): title, hook line, sections with a style each, 1 to 3 custom hero moments.
  Hook votes (Jev Router x3, in parallel with stage A): majority check on the hook.
  Stage B (Jev Router, every non-hero beat at once): graphic component, on-screen text, landing word.
Every answer is schema-checked (plan_schema.py); a failure retries once on Claude with the error.

Usage:  plan_fast.py <project> [--brief "what the reel is for"] [--out work/plan_fast.json]
Reads <project>/edl.json (id + line per segment). Needs OPENROUTER_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llm_router as LR
import plan_schema as PS

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
VOTES = 3
WORKERS = 32


def load_lines(proj: Path) -> dict:
    edl = json.loads((proj / "edl.json").read_text())
    segs = edl if isinstance(edl, list) else edl.get("segments", [])
    lines = {s["id"]: s["line"].strip() for s in segs if s.get("id") and s.get("line", "").strip()}
    if not lines:
        raise SystemExit(f"no lines found in {proj / 'edl.json'}")
    return lines


def menus() -> tuple[str, str]:
    cat = json.loads((SKILL / "styles" / "catalog.json").read_text())["styles"]
    styles = "\n".join(f"- {s['id']}: {s['desc']}" for s in cat if s["id"] in PS.STYLES)
    sys.path.insert(0, str(SKILL / "templates" / "kit"))
    import rrkit  # noqa: E402  (kit registry: what each graphic does)
    comps = "\n".join(f"- {k}: {v.get('what', '')}" for k, v in rrkit.COMPONENTS.items() if not v.get("hero"))
    comps += "\n- behind-head-word: one huge word behind the speaker's head (cut-out styles)\n- none: no graphic"
    return styles, comps


def hero_menu() -> str:
    """The hero library (one line each) so Claude's hero ideas can name a library id when one fits."""
    import hero_schema as HS
    return HS.catalog_text(compact=True)


def reel_prompt(lines: dict, brief: str, styles: str) -> str:
    listing = "\n".join(f"{k}: {v}" for k, v in lines.items())
    return f"""You are a world-class short-form video editor and motion designer planning an Instagram reel.
Brief: {brief}

Transcript lines in order (id: line):
{listing}

Visual styles available:
{styles}

Plan the whole reel. JSON only:
{{"title": "on-screen hook title, max {PS.MAX_TITLE} chars, no em dash",
  "hook_id": "the line id that should open the reel (can be pulled forward)",
  "sections": [{{"name": "short", "style": one of {PS.STYLES}, "purpose": one of {PS.PURPOSES},
                "line_ids": [consecutive ids]}}],
  "hero_moments": [{{"line_id": id, "anchor_word": "a word copied from that line",
                    "idea": "a bespoke, jaw-dropping visual built for this exact line (2 sentences)",
                    "library": "a hero library id when one fits this line, else omit"}}]}}
Hero library (premium, ready-made hero moments; name one in "library" when it fits, keep the idea free-form when
nothing fits):
{hero_menu()}
Rules: sections cover every id exactly once in transcript order; change style when the topic turns;
1 to {PS.MAX_HEROES} hero moments on the lines that matter most (prefer library heroes when they fit); ideas must be
specific, never a generic label."""


def beat_prompt(lid: str, lines: dict, section: dict, comps: str) -> str:
    ids = list(lines)
    i = ids.index(lid)
    prev = lines[ids[i - 1]] if i else "(start)"
    nxt = lines[ids[i + 1]] if i + 1 < len(ids) else "(end)"
    return f"""Reel section "{section['name']}" in style {section['style']} (purpose: {section['purpose']}).
Previous line: {prev}
THIS LINE: {lines[lid]}
Next line: {nxt}

Graphics available:
{comps}

Choose the graphic for THIS LINE. A graphic must add information (a number, a list, an action, a contrast),
not repeat the words. On-screen text uses ONLY words and numbers the speaker actually says here; never invent
stats, prompts or claims. Use "none" for connective lines. JSON only:
{{"component": one of {PS.COMPONENTS}, "on_screen_text": "max {PS.MAX_TEXT} chars or empty",
  "anchor_word": "one word copied exactly from THIS LINE", "why": "max 12 words"}}"""


def vote_prompt(lines: dict, brief: str) -> str:
    listing = "\n".join(f"{k}: {v}" for k, v in lines.items())
    return (f"Brief: {brief}\nTranscript lines:\n{listing}\n\nWhich single line is the strongest scroll-stopping "
            'opening hook? JSON only: {"best_id": id}')


def stage_a(pool, lines, brief, styles):
    """Run the Claude reel plan and the Jev hook votes concurrently."""
    plan_f = pool.submit(LR.typed, reel_prompt(lines, brief, styles),
                         lambda d: PS.check_reel_plan(d, lines), (LR.STRONG, LR.STRONG), 3000)
    vote_fs = [pool.submit(LR.typed, vote_prompt(lines, brief), PS.check_vote(list(lines)), (LR.ROUTER, LR.FAST), 600)
               for _ in range(VOTES)]
    return plan_f.result(), [f.result() for f in vote_fs]


def stage_b(pool, lines, plan, comps):
    heroes = {h["line_id"]: h for h in plan["hero_moments"]}
    section_of = {lid: s for s in plan["sections"] for lid in s["line_ids"]}
    ids = list(lines)

    def context(lid):
        i = ids.index(lid)
        return " ".join(lines[j] for j in ids[max(0, i - 1):i + 2] if j != lid)
    jobs = {lid: pool.submit(LR.typed, beat_prompt(lid, lines, section_of[lid], comps),
                             PS.check_beat(lines[lid], context(lid)))
            for lid in lines if lid not in heroes}
    beats = []
    for lid, line in lines.items():
        sec = section_of[lid]
        base = {"id": lid, "line": line, "section": sec["name"], "style": sec["style"], "purpose": sec["purpose"]}
        if lid in heroes:
            h = heroes[lid]
            beats.append({**base, "hero": True, "component": "custom", "anchor_word": h["anchor_word"],
                          "visual_intent": h["idea"], "attempts": [],
                          **({"library": h["library"]} if h.get("library") else {})})
            continue
        res = jobs[lid].result()
        d = res["data"] or {"component": "none", "on_screen_text": "", "anchor_word": ""}
        beats.append({**base, "hero": False, **{k: d.get(k, "") for k in ("component", "on_screen_text",
                      "anchor_word", "why")}, "unresolved": res["data"] is None, "attempts": res["attempts"]})
    return beats


def hook_verdict(plan, votes):
    tally = Counter(v["data"]["best_id"] for v in votes if v["data"])
    tally[plan["hook_id"]] += 1
    top, n = tally.most_common(1)[0]
    return {"claude": plan["hook_id"], "votes": dict(tally), "pick": top, "agreement": round(n / (VOTES + 1), 2)}


def summarize(t0, plan_res, votes, beats):
    attempts = plan_res["attempts"] + [a for v in votes for a in v["attempts"]] + \
        [a for b in beats for a in b["attempts"]]
    return {"wall_secs": round(time.time() - t0, 2), "calls": len(attempts),
            "retries": sum(1 for a in attempts if a["error"]),
            "unresolved_beats": sum(1 for b in beats if b.get("unresolved")),
            "cost_usd": round(sum(a["cost"] or 0 for a in attempts), 5),
            "models": dict(Counter(a["model"] for a in attempts))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--brief", default="Instagram reel. Fast, cinematic, premium. Make the viewer stop and save it.")
    ap.add_argument("--out", default="work/plan_fast.json")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    lines = load_lines(proj)
    styles, comps = menus()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        plan_res, votes = stage_a(pool, lines, a.brief, styles)
        if plan_res["data"] is None:
            print("reel plan failed:", plan_res["attempts"][-1]["error"], file=sys.stderr)
            return 1
        t_a = round(time.time() - t0, 2)
        beats = stage_b(pool, lines, plan_res["data"], comps)
    plan = plan_res["data"]
    out = {"title": plan["title"], "hook": hook_verdict(plan, votes), "sections": plan["sections"],
           "hero_moments": plan["hero_moments"], "beats": beats,
           "stats": {**summarize(t0, plan_res, votes, beats), "stage_a_secs": t_a}}
    dest = proj / a.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(json.dumps(out["stats"], indent=1))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
