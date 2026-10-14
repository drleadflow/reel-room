#!/usr/bin/env python3
"""Vision judge: a video model watches a clip and scores it against a fixed yes/no rubric.

  judge.py <video ...> [--kind hero|reel] [--intent "what it should show"] [--ref REF] [--strong] [--json] [--out FILE]
With --ref, each clip is compared side by side against a reference clip that sets the bar (for example
a hand-built showcase reel); it passes only if it is not worse than the reference on any criterion.
Pairwise comparison is far more reliable than absolute 0-10 scores, which cluster around 6.
Exit 0 when every clip passes, 1 otherwise. Clips are judged in parallel; each is shrunk to a small
analysis copy first (360 px wide, 12 fps), so a call takes about 20 to 40 s.

The verdict is typed and validated (see check_verdict); a malformed answer retries on the next model.
This replaces an agent eyeballing frames for taste. Exact rules (safe zone, spacing, loudness) stay in
qa.py; the judge covers what code cannot measure: readability at phone size, timing to the word,
premium vs AI-slop look, and visual bugs. Needs OPENROUTER_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llm_router as LR

CHAIN = (LR.FAST, "google/gemini-3.7-flash", LR.ROUTER)
STRONG_CHAIN = ("google/gemini-4-argon", LR.FAST)
VERDICTS = ("worse", "same", "better")
PASS_SCORE = 7          # every criterion must reach this (0 to 10)
# Timing to the word is measured exactly by code (word times + kit_meta); the model's timing calls at 12 fps
# disagreed with measured times, so on_word is reported as advice and does not decide pass/fail.
ADVISORY = {"on_word"}
MAX_MB = 6
CRITERIA = {
    "readable": "every word on screen is readable on a phone at a glance, nothing clipped, cramped or overlapping",
    "on_word": "graphics and type land on the spoken word they belong to, not early or late",
    "premium": "looks like a top motion designer made it: clean hierarchy, eased motion, no clip-art or AI-slop look",
    "face_clear": "the speaker's face is never covered by text or graphics",
    "motion": "motion is smooth with no stutter, frozen frames, flicker, jumps or half-rendered states",
    "purpose": "the visual clearly shows the idea it is meant to show",
}
KIND_NOTE = {
    "hero": "This is a short hero animation clip from a reel kit, possibly over a talking-head plate.",
    "reel": "This is a full vertical short-form reel (Instagram/TikTok).",
}


def small_copy(src: Path, tmp: Path) -> Path:
    """360 px wide, 12 fps, low bitrate H.264 so the clip fits inline in one request."""
    out = tmp / (src.stem + "_" + str(abs(hash(str(src))) % 10**6) + "_judge.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale=540:-2,fps=12", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-b:a", "48k", "-ac", "1", str(out)]
    subprocess.run(cmd, check=True, timeout=600)
    if out.stat().st_size > MAX_MB * 1_000_000:
        raise ValueError(f"{src.name}: analysis copy over {MAX_MB} MB; judge a shorter clip")
    return out


def prompt(kind: str, intent: str) -> str:
    crit = "\n".join(f'- "{k}": {v}' for k, v in CRITERIA.items())
    return f"""You are a strict senior motion designer reviewing work before a client sees it.
{KIND_NOTE[kind]}
Intended effect: {intent or "not given; judge it on its own"}

Watch the whole clip, picture and audio. Score each criterion 0 to 10 (7 = acceptable for a premium brand):
{crit}

JSON only:
{{"scores": {{{", ".join(f'"{k}": int' for k in CRITERIA)}}},
  "issues": [{{"t": seconds, "criterion": one of {list(CRITERIA)}, "issue": "what is wrong (max 20 words)",
              "fix": "concrete fix (max 20 words)"}}],
  "best_moment": seconds, "summary": "one sentence"}}
List an issue for every criterion scored below {PASS_SCORE}. Be specific with timestamps; do not invent issues."""


def check_verdict(d: dict) -> str | None:
    scores = d.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(CRITERIA):
        return f"scores must have exactly these keys: {list(CRITERIA)}"
    for k, v in scores.items():
        if not isinstance(v, int) or not 0 <= v <= 10:
            return f"score {k} must be an integer 0 to 10"
    issues = d.get("issues")
    if not isinstance(issues, list):
        return "issues must be a list"
    for it in issues:
        if it.get("criterion") not in CRITERIA or not it.get("issue") or not isinstance(it.get("t"), (int, float)):
            return "each issue needs t (seconds), a valid criterion, issue and fix"
    low = {k for k, v in scores.items() if v < PASS_SCORE}
    missing = low - {it["criterion"] for it in issues}
    if missing:
        return f"criteria scored below {PASS_SCORE} need an issue each: {sorted(missing)}"
    return None


def compare_prompt(kind: str, intent: str) -> str:
    crit = "\n".join(f'- "{k}": {v}' for k, v in CRITERIA.items())
    return f"""You are a strict senior motion designer. Two vertical clips follow: the FIRST is the CANDIDATE,
the SECOND is the REFERENCE, a hand-made edit that sets the quality bar. {KIND_NOTE[kind]}
Intended effect of the candidate: {intent or "not given"}

For each criterion, is the CANDIDATE worse than, the same as, or better than the REFERENCE?
{crit}

JSON only:
{{"compare": {{{", ".join(f'"{k}": "worse|same|better"' for k in CRITERIA)}}},
  "issues": [{{"t": seconds in the CANDIDATE, "criterion": one of {list(CRITERIA)}, "issue": "max 20 words",
              "fix": "concrete fix to reach the reference (max 20 words)"}}],
  "summary": "one sentence on the biggest gap"}}
List an issue for every criterion marked worse. Judge craft, not topic: the two clips may be about different subjects."""


def check_compare(d: dict) -> str | None:
    comp = d.get("compare")
    if not isinstance(comp, dict) or set(comp) != set(CRITERIA):
        return f"compare must have exactly these keys: {list(CRITERIA)}"
    if any(v not in VERDICTS for v in comp.values()):
        return f"each compare value must be one of {VERDICTS}"
    issues = d.get("issues")
    if not isinstance(issues, list):
        return "issues must be a list"
    for it in issues:
        if it.get("criterion") not in CRITERIA or not it.get("issue") or not isinstance(it.get("t"), (int, float)):
            return "each issue needs t (seconds), a valid criterion, issue and fix"
    missing = {k for k, v in comp.items() if v == "worse"} - {it["criterion"] for it in issues}
    return f"criteria marked worse need an issue each: {sorted(missing)}" if missing else None


def compare_one(path: str, ref_part: dict, kind: str, intent: str, tmp: Path, chain) -> dict:
    src = Path(path).expanduser()
    try:
        part = LR.video_part(small_copy(src, tmp))
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        return {"video": str(src), "pass": False, "error": str(exc), "attempts": []}
    res = LR.typed(compare_prompt(kind, intent), check_compare, chain, 2500, [part, ref_part])
    d = res["data"]
    if not d:
        return {"video": str(src), "pass": False, "error": "no valid verdict", "attempts": res["attempts"]}
    ok = all(v != "worse" for k, v in d["compare"].items() if k not in ADVISORY)
    return {"video": str(src), "pass": ok, **d, "attempts": res["attempts"]}


def judge_one(path: str, kind: str, intent: str, tmp: Path, chain=CHAIN) -> dict:
    src = Path(path).expanduser()
    try:
        part = LR.video_part(small_copy(src, tmp))
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        return {"video": str(src), "pass": False, "error": str(exc), "attempts": []}
    res = LR.typed(prompt(kind, intent), check_verdict, chain, 2500, [part])
    d = res["data"]
    if not d:
        return {"video": str(src), "pass": False, "error": "no valid verdict", "attempts": res["attempts"]}
    ok = all(v >= PASS_SCORE for k, v in d["scores"].items() if k not in ADVISORY)
    return {"video": str(src), "pass": ok, **d, "attempts": res["attempts"]}


def report_line(r: dict) -> str:
    if r.get("error"):
        return f"FAIL {Path(r['video']).name}: {r['error']}"
    marks = r.get("scores") or r.get("compare") or {}
    sc = " ".join(f"{k}={v}" for k, v in marks.items())
    head = f"{'PASS' if r['pass'] else 'FAIL'} {Path(r['video']).name}: {sc}"
    fixes = [f"   {i['t']:.1f}s [{i['criterion']}] {i['issue']} -> {i.get('fix', '')}" for i in r.get("issues", [])]
    return "\n".join([head, *fixes])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--kind", choices=list(KIND_NOTE), default="hero")
    ap.add_argument("--intent", default="")
    ap.add_argument("--ref", help="reference clip that sets the bar (pairwise mode)")
    ap.add_argument("--strong", action="store_true", help="use the stronger (slower, pricier) vision model first")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="write the full verdicts as JSON here")
    a = ap.parse_args(argv)
    chain = STRONG_CHAIN if a.strong else CHAIN
    with tempfile.TemporaryDirectory() as td, ThreadPoolExecutor(max_workers=min(8, len(a.videos))) as pool:
        if a.ref:
            ref_part = LR.video_part(small_copy(Path(a.ref).expanduser(), Path(td)))
            run = lambda v: compare_one(v, ref_part, a.kind, a.intent, Path(td), chain)  # noqa: E731
        else:
            run = lambda v: judge_one(v, a.kind, a.intent, Path(td), chain)  # noqa: E731
        results = list(pool.map(run, a.videos))
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=1))
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            print(report_line(r))
        cost = sum(x.get("cost") or 0 for r in results for x in r.get("attempts", []))
        print(f"judged {len(results)} clip(s), {sum(r['pass'] for r in results)} passed, ${cost:.4f}")
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
