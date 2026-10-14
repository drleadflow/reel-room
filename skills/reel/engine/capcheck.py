#!/usr/bin/env python3
"""Caption phrasing check on the composed captions (layout_boxes.json).

  python capcheck.py <project> [--out FILE] [--json]

FAIL when
  - a caption ends on a binding word (the phrase obviously continues: 'to', 'of', 'per', 'the', ...) or splits a
    number from its unit or range, while the next caption follows within 0.4 s (no pause to excuse the break)
  - two captions overlap in time
  - a one-word caption sits between captions with no pause around it (orphan), unless the style is word-by-word
    (explicit caption_mode "word", or nearly every caption is a single word); "also" is exempt.

Captions are read from layout_boxes.json in any shape the engine writes: {captions:[{t0,t1,text,hidden?}]}, or boxes
whose kind/type/role contains "caption" ({beats:[{boxes}]}, {boxes:[...]} or a plain list). Hidden captions are
ignored. No caption list -> skipped. A break between captions of different segments (their `seg`) or on a cut
(segments.json, within 2.5 frames) is forced by the edit and allowed (no binding-word or number check there), and so is
a one-word caption next to a segment boundary (including a one-word segment).
Writes <project>/qa/capcheck.json (or --out). Exit code 0 = pass, 1 = fail, 2 = could not run.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

BIND = {"a", "an", "the", "to", "of", "per", "and", "or", "for", "at", "your", "my", "in", "on", "with", "that", "about",
        "if", "can", "only", "is", "than", "versus", "how", "many", "you", "you're", "i'll", "from", "this", "so", "but",
        "be", "should", "max", "found"}
NUM = re.compile(r"^~?\d+(\.\d+)?$")
END_PUNCT = re.compile(r"[.,?!;:]$")
PAUSE = 0.4              # seconds; a break followed by a pause this long is fine
OVERLAP_EPS = 1e-3
WORD_MODE_RATIO = 1.1    # words per caption at or below this = word-by-word style
ORPHAN_OK = {"also"}
LABEL = "Captions break at natural pauses"
CUT_TOL = 2.5 / 30       # a caption break within 2.5 frames of a cut is forced by the cut, not a phrasing choice


def bare(t):
    return re.sub(r"[^\w.'~-]", "", t.lower()).rstrip(".")


# ----------------------------------------------------------------------------- loading
def _flat_boxes(raw):
    if isinstance(raw, dict) and "beats" in raw:
        return [b for beat in raw["beats"] for b in beat.get("boxes", [])]
    boxes = raw.get("boxes", []) if isinstance(raw, dict) else raw
    return boxes if isinstance(boxes, list) else []


def _is_caption(b):
    kind = str(b.get("kind") or b.get("type") or b.get("role") or "").lower()
    return "caption" in kind


def _cap(b):
    t0, t1 = b.get("t0", b.get("start")), b.get("t1", b.get("end"))
    if t0 is None or t1 is None or not str(b.get("text", "")).strip():
        return None
    c = {"text": str(b["text"]).strip(), "t0": float(t0), "t1": float(t1)}
    if b.get("seg") is not None:
        c["seg"] = b["seg"]
    return c


def captions_from_layout(raw):
    """(captions sorted by t0, explicit caption mode or None) from any layout_boxes.json shape; None if no captions."""
    if isinstance(raw, dict) and isinstance(raw.get("captions"), list):
        src, mode = raw["captions"], raw.get("caption_mode")
    else:
        src = [b for b in _flat_boxes(raw) if isinstance(b, dict) and _is_caption(b)]
        mode = raw.get("caption_mode") if isinstance(raw, dict) else None
    caps, seen = [], set()
    for b in src:
        c = _cap(b) if isinstance(b, dict) and not b.get("hidden") else None
        key = c and (c["text"], round(c["t0"], 3), round(c["t1"], 3))
        if c and key not in seen:
            seen.add(key)
            caps.append(c)
    if not caps:
        return None, mode
    return sorted(caps, key=lambda c: (c["t0"], c["t1"])), mode


# ----------------------------------------------------------------------------- rules (pure)
def is_word_mode(caps, mode=None):
    if str(mode or "").lower() == "word":
        return True
    return sum(len(c["text"].split()) for c in caps) <= WORD_MODE_RATIO * len(caps)


def at_cut(t0, t1, cuts):
    """True when a cut falls in the gap between t0 (end of one caption) and t1 (start of the next), with tolerance"""
    return any(t0 - CUT_TOL <= c <= t1 + CUT_TOL for c in cuts)


def cut_forced(a, b, cuts):
    """the break a|b is forced by the edit: the captions belong to different segments (their `seg`), or a cut from
    segments.json falls between them. Captions never span a cut, so no chunker can fix these."""
    if a is None or b is None:
        return True
    if a.get("seg") is not None and b.get("seg") is not None and a["seg"] != b["seg"]:
        return True
    return at_cut(a["t1"], b["t0"], cuts)


def break_findings(caps, cuts=()):
    """Time overlaps and mid-phrase breaks between neighbouring captions. A break that sits on a cut (segments.json)
    is forced by the edit (captions never run across a cut), so it is allowed."""
    bad = []
    for a, b in zip(caps, caps[1:]):
        if b["t0"] < a["t1"] - OVERLAP_EPS:
            bad.append(f"overlap {a['text']!r} / {b['text']!r} at {b['t0']:.2f}")
        ws = a["text"].split()
        if cut_forced(a, b, cuts):
            continue
        if len(ws) > 1 and not END_PUNCT.search(ws[-1]) and b["t0"] - a["t1"] < PAUSE:
            last = bare(ws[-1])
            if last in BIND or NUM.match(last):
                bad.append(f"mid-phrase break at {a['t1']:.2f}: {a['text']!r} | {b['text']!r}")
    return bad


def orphan_findings(caps, cuts=()):
    bad = []
    for i, c in enumerate(caps):
        if len(c["text"].split()) != 1 or c["text"].strip(".,?!").lower() in ORPHAN_OK:
            continue
        prev_end = caps[i - 1]["t1"] if i else -9.0
        nxt = caps[i + 1]["t0"] if i + 1 < len(caps) else 99.0e3
        prev, after = (caps[i - 1] if i else None), (caps[i + 1] if i + 1 < len(caps) else None)
        if cut_forced(prev, c, cuts) or cut_forced(c, after, cuts):
            continue                       # a lone word next to a cut (or a one-word segment), not a phrasing choice
        if c["t0"] - prev_end < PAUSE or nxt - c["t1"] < PAUSE:
            bad.append(f"orphan word {c['text']!r} at {c['t0']:.2f}")
    return bad


def phrasing_findings(caps, mode=None, cuts=()):
    """All phrasing problems for captions [{text,t0,t1}] (sorted by t0). mode='word' marks word-by-word style.
    cuts = cut times in seconds (breaks on a cut are allowed)."""
    caps = [c for c in caps if not c.get("hidden")]
    return break_findings(caps, cuts) + ([] if is_word_mode(caps, mode) else orphan_findings(caps, cuts))


def cut_times(proj):
    """cut times (s) from segments.json: the first frame of every segment after the first"""
    p = Path(proj) / "segments.json"
    try:
        segs = C.read_json(p) if p.is_file() else []
        return [s["frame"] / C.FPS for s in segs[1:] if "frame" in s]
    except (ValueError, TypeError, KeyError):
        return []


# ----------------------------------------------------------------------------- run / check / cli
class CapcheckSkip(Exception):
    pass


def run(project, out=None):
    """Judge the captions and write the report (default <project>/qa/capcheck.json). Raises CapcheckSkip."""
    proj = Path(project).expanduser().resolve()
    lb = proj / "layout_boxes.json"
    if not lb.is_file():
        raise CapcheckSkip(f"no layout_boxes.json in {proj}")
    try:
        raw = C.read_json(lb)
    except ValueError as e:
        raise CapcheckSkip(f"layout_boxes.json is not valid JSON ({e})") from e
    caps, mode = captions_from_layout(raw)
    if not caps:
        raise CapcheckSkip("no captions in layout_boxes.json")
    cuts = cut_times(proj)
    bad = phrasing_findings(caps, mode, cuts)
    report = {"project": str(proj), "captions": len(caps), "word_mode": is_word_mode(caps, mode), "cuts": len(cuts),
              "pass": not bad, "findings": bad}
    C.write_json(out or proj / "qa" / "capcheck.json", report)
    return report


def check(project, out=None):
    """qa.py check shape {name, pass, detail, label[, skipped]}."""
    base = {"name": "caption_phrasing", "label": LABEL}
    try:
        rep = run(project, out)
    except CapcheckSkip as e:
        return {**base, "pass": True, "skipped": True, "detail": f"skipped: {e}"}
    bad = rep["findings"]
    if not bad:
        return {**base, "pass": True, "detail": f"{rep['captions']} captions, every break lands on a pause or phrase end"}
    more = "; ..." if len(bad) > 3 else ""
    return {**base, "pass": False, "detail": f"{len(bad)} caption break problem{'s' if len(bad) != 1 else ''}: "
                                             + "; ".join(bad[:3]) + more}


def main():
    ap = argparse.ArgumentParser(description="Caption phrasing check (layout_boxes.json).")
    ap.add_argument("project")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = C.Out(a.json)
    try:
        rep = run(a.project, a.out)
    except CapcheckSkip as e:
        C.fail(str(e), "Build the composition first: the template writes layout_boxes.json with the captions.", a.json)
    out.log(f"CAPCHECK {'PASS' if rep['pass'] else 'FAIL'}: {rep['captions']} captions"
            + (" (word-by-word)" if rep["word_mode"] else ""))
    for x in rep["findings"]:
        out.log("  ", x)
    out.result(rep)
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
