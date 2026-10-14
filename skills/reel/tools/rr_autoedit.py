"""First-pass edit for `reel demo <clip>` (no Claude in the loop, no API key): the user's own words become the edit
list and a plan that validate_plan.py accepts. /reel in Claude Code does this properly (take picking by ear, a plan
written for the reel); this is the quick look.

  edl.json    one segment per spoken phrase from the transcript; pauses over PAUSE s are cut out; an earlier take
              is dropped when the next phrase starts with the same 3 words (a retake); layouts alternate so every
              cut shows a new picture
  plan.json   title from the opening words, one hero on the line with a number (else the longest line), a counter
              on every other line that says a number, captions only elsewhere; only words and numbers the speaker
              said, checked with the planner's own rules (plan_schema)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PAUSE = 0.45          # a gap this long ends a phrase
MAX_SEG = 7.0         # a phrase longer than this ends at the next sentence or comma
MIN_SEG = 1.0
STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "your", "you", "i", "my", "with",
        "that", "this", "so", "but", "if", "are", "was", "be", "do", "just", "like", "um", "uh"}
NUM = re.compile(r"^\$?\d[\d,.]*%?$")


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def phrases(words: list) -> list:
    """[[word, ...], ...]: split at pauses, at sentence ends once long enough, and hard at MAX_SEG"""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (w["s"] - cur[-1]["e"] >= PAUSE):
            out.append(cur)
            cur = []
        cur.append(w)
        dur = cur[-1]["e"] - cur[0]["s"]
        end = w["w"].rstrip().endswith((".", "?", "!"))
        comma = w["w"].rstrip().endswith(",")
        if (end and dur >= 2.5) or (dur >= MAX_SEG and (end or comma)) or dur >= MAX_SEG + 3:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [p for p in out if p[-1]["e"] - p[0]["s"] >= MIN_SEG or len(p) >= 3]


def drop_retakes(ph: list) -> list:
    keep = []
    for i, p in enumerate(ph):
        nxt = ph[i + 1] if i + 1 < len(ph) else None
        head = [norm(w["w"]) for w in p[:3]]
        if nxt and len(p) >= 2 and head == [norm(w["w"]) for w in nxt[:3]]:
            continue                                    # the next phrase is a retake of this one: keep the last
        keep.append(p)
    return keep


def edl_from(words: list, clip: str = "c1") -> list:
    ph = drop_retakes(phrases(words))
    edl = []
    for i, p in enumerate(ph, 1):
        line = " ".join(w["w"].strip() for w in p).replace(" ,", ",").strip()
        edl.append({"id": f"s{i}", "clip": clip, "in": round(max(0.0, p[0]["s"] - 0.05), 2),
                    "out": round(p[-1]["e"] + 0.08, 2), "mode": "split" if i % 2 else "full", "zoom": 1.0,
                    "cx": 0.5, "cy": 0.43, "line": line})
    return edl


def _tokens(line: str) -> list:
    return [t.strip(".,!?;:'\"()") for t in line.split() if t.strip(".,!?;:'\"()")]


def number_text(line: str):
    """(on-screen text, anchor) for the first number in the line: the number and the word after it, if short"""
    toks = _tokens(line)
    for i, t in enumerate(toks):
        if NUM.match(t):
            nxt = toks[i + 1] if i + 1 < len(toks) and toks[i + 1].lower() not in STOP else ""
            text = f"{t} {nxt}".strip()
            return (text if len(text) <= 28 else t), t
    return None


def anchor_of(line: str) -> str:
    toks = [t for t in _tokens(line) if t.lower() not in STOP]
    return max(toks, key=len) if toks else _tokens(line)[0]


def title_of(line: str) -> str:
    words, out = _tokens(line), []
    for w in words:
        if len(" ".join(out + [w])) > 34:
            break
        out.append(w)
    return " ".join(out).upper() or "MY REEL"


def plan_from(edl: list, style: str) -> dict:
    import plan_schema as PS
    lines = {s["id"]: s["line"] for s in edl}
    ids = list(lines)
    with_num = [i for i in ids if number_text(lines[i])]
    hero = with_num[0] if with_num else max(ids, key=lambda i: len(lines[i]))
    sections = [{"name": "hook", "style": style, "purpose": "hook", "line_ids": ids[:1]}]
    if len(ids) > 2:
        sections.append({"name": "body", "style": style, "purpose": "explain", "line_ids": ids[1:-1]})
    if len(ids) > 1:
        sections.append({"name": "close", "style": style, "purpose": "cta", "line_ids": ids[-1:]})
    word = (number_text(lines[hero]) or (None, anchor_of(lines[hero])))[1]
    plan = {"title": title_of(lines[ids[0]]), "hook_id": ids[0], "sections": sections,
            "hero_moments": [{"line_id": hero, "anchor_word": word,
                              "idea": f"The key line lands big on '{word}', the moment the viewer should remember."}],
            "beats": []}
    for i, lid in enumerate(ids):
        if lid == hero:
            continue
        nt = number_text(lines[lid])
        ctx = " ".join(lines[j] for j in ids[max(0, i - 1):i + 2] if j != lid)
        beat = {"id": lid, "component": "none", "on_screen_text": "", "anchor_word": "", "why": "captions carry it"}
        if nt:
            cand = {"id": lid, "component": "odometer", "on_screen_text": nt[0], "anchor_word": nt[1],
                    "why": "the number is the point of this line"}
            if PS.check_beat(lines[lid], ctx)(cand) is None:
                beat = cand
        plan["beats"].append(beat)
    return plan


def write(proj: Path, style: str) -> tuple:
    words = json.loads((proj / "work" / "words_c1_fast.json").read_text())
    if len(words) < 8:
        raise SystemExit("I could not hear enough speech in this clip (fewer than 8 words). Use a clip where you "
                         "talk for 20 to 60 seconds.")
    edl = edl_from(words)
    if len(edl) < 2:
        raise SystemExit("The clip has only one phrase. Talk for 20 to 60 seconds with a few short pauses.")
    (proj / "edl.json").write_text(json.dumps(edl, indent=1))
    plan = plan_from(edl, style)
    (proj / "work" / "plan_draft.json").write_text(json.dumps(plan, indent=1))
    return edl, plan
