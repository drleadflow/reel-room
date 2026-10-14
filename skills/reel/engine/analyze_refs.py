#!/usr/bin/env python3
"""Reference reel breakdown: a vision model watches each reel and returns a typed beat map; a second
pass turns all of them into a ranked "what to steal" list mapped onto our kit and styles.

  analyze_refs.py <out_dir> <video ...> [--creator NAME]
Videos should be small analysis copies (360p, 12 fps, a few MB). Writes <out_dir>/ref_<n>.json and
<out_dir>/steal.json. Analysis only: never reuse another creator's footage in an output.
Needs OPENROUTER_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llm_router as LR
import plan_schema as PS

LAYOUTS = ["talking-head", "split-top-broll", "full-broll", "screen-recording", "cutout", "graphic-card",
           "text-only", "pip"]
EXTRA = ["broll-clip", "screen-demo", "ai-generated-broll", "meme-or-reaction", "new"]
MATCHES = PS.COMPONENTS + EXTRA
HOOKS = ["contrarian", "receipt-number", "curiosity-gap", "story", "question", "callout", "demo-first", "news"]
VISION_CHAIN = (LR.ROUTER, LR.FAST, "google/gemini-3.7-flash")
MIN_BEATS = 8


def ref_prompt(creator: str) -> str:
    return f"""You are a senior short-form video editor. Watch this {creator} reel closely (picture AND audio).
Break it into beats (one per visual change, typically 0.5 to 4 s). JSON only:
{{"hook": {{"first_3s_visual": str, "first_line": "exact words", "on_screen_text": str,
           "hook_type": one of {HOOKS}}},
  "beats": [{{"start": seconds, "end": seconds, "line": "what is said", "layout": one of {LAYOUTS},
             "visual": "exactly what is on screen and how it moves (max 25 words)",
             "kit_match": one of {MATCHES}, "new_device": "name it if kit_match is new, else empty",
             "transition_in": "cut | whip | zoom | push | flash | match-cut | none | other: ...",
             "purpose": one of {PS.PURPOSES}}}],
  "caption_style": "font, size, position, how words appear", "sound": "music, sfx, risers, silence",
  "signature_moves": ["3 to 6 repeatable techniques, each concrete"],
  "pacing_note": "how pace changes across the reel"}}"""


def check_ref(d: dict) -> str | None:
    hook = d.get("hook") or {}
    if hook.get("hook_type") not in HOOKS:
        return f"hook_type must be one of {HOOKS}"
    beats = d.get("beats")
    if not isinstance(beats, list) or len(beats) < MIN_BEATS:
        return f"need at least {MIN_BEATS} beats, one per visual change"
    last = -1.0
    for b in beats:
        if b.get("layout") not in LAYOUTS:
            return f"bad layout {b.get('layout')!r}"
        if b.get("kit_match") not in MATCHES:
            return f"bad kit_match {b.get('kit_match')!r}"
        if b["kit_match"] == "new" and not b.get("new_device"):
            return "name the new_device when kit_match is new"
        start = float(b.get("start", -1))
        if start < last or not b.get("visual"):
            return "beats must be in time order with a visual description"
        last = start
    if not 3 <= len(d.get("signature_moves") or []) <= 6:
        return "give 3 to 6 signature_moves"
    return None


def steal_prompt(refs: list, creator: str) -> str:
    styles = ", ".join(PS.STYLES)
    comps = ", ".join(PS.COMPONENTS)
    return f"""Here are typed breakdowns of {len(refs)} reels by {creator}:
{json.dumps(refs)[:60000]}

Our system has visual styles [{styles}] and animated kit components [{comps}].
Decide what we should steal for our reel engine. JSON only:
{{"system_summary": "how this creator edits, 3 sentences",
  "steal": [{{"move": "the technique", "seen_in": number of reels (1-{len(refs)}),
             "how_we_build_it": "concrete build note for our engine (max 30 words)",
             "maps_to": "an existing style or component id, or new:<name>", "priority": "high|med|low"}}],
  "pacing_targets": {{"avg_shot_sec": number, "broll_share": 0-1, "text_on_screen_share": 0-1}},
  "hook_patterns": ["concrete patterns from the first 3 s"],
  "avoid": ["things that would look like a copy or not fit a physician creator"]}}
List 8 to 14 steal items, most valuable first."""


def check_steal(d: dict) -> str | None:
    items = d.get("steal")
    if not isinstance(items, list) or not 8 <= len(items) <= 14:
        return "steal needs 8 to 14 items"
    known = set(PS.STYLES) | set(PS.COMPONENTS)
    for it in items:
        m = str(it.get("maps_to", ""))
        if m not in known and not m.startswith("new:"):
            return f"maps_to {m!r} must be a style, a component, or new:<name>"
        if it.get("priority") not in ("high", "med", "low"):
            return "priority must be high, med or low"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--creator", default="this creator")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(a.videos)) as pool:
        futs = [pool.submit(LR.typed, ref_prompt(a.creator), check_ref, VISION_CHAIN, 6000,
                            [LR.video_part(v)]) for v in a.videos]
        results = [f.result() for f in futs]
    refs = []
    for i, (v, r) in enumerate(zip(a.videos, results), 1):
        (out / f"ref_{i}.json").write_text(json.dumps({"video": v, **r}, indent=1))
        if r["data"]:
            refs.append({"video": Path(v).name, **r["data"]})
        print(f"ref {i}: {'ok' if r['data'] else 'FAILED'} via {r['attempts'][-1]['model']} "
              f"({sum(x['secs'] for x in r['attempts'])}s, {len(r['attempts'])} tries)")
    if not refs:
        return 1
    steal = LR.typed(steal_prompt(refs, a.creator), check_steal, (LR.STRONG, LR.STRONG), 5000)
    (out / "steal.json").write_text(json.dumps(steal, indent=1))
    cost = sum(x["cost"] or 0 for r in results + [steal] for x in r["attempts"])
    print(f"steal: {'ok' if steal['data'] else 'FAILED'} | total {round(time.time() - t0, 1)}s, ${round(cost, 4)}")
    return 0 if steal["data"] else 1


if __name__ == "__main__":
    sys.exit(main())
