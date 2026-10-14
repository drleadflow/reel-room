"""motion-editorial adapter: paper stage on top, speaker in a rounded card below, one-word captions (plain swaps).

  none  -> full close-up (caption only; back-to-back caption-only cuts alternate a punch-in)
  word  -> card + kinetic (one line, sized to read big; hero: accent, slams in)
  list  -> card + cred_stack (01 / 02 / 03 lines on their words)
  stat  -> card + kit odometer (rolls onto its word; big_stat clips wide values and leaves an empty label box)
  typer -> card + kit typer          flow -> card + kinetic (left serif accent, arrow, right sans)
  cta   -> card + kit comment-cta    phone -> full + kit phone-frame
  hero  -> card + the library hero on the paper stage (cream set), or full frame for frame heroes
The hook title is the style's title_card overlay over the first segment. No cut-out: behind-head words become
kinetic words on the stage.
"""
from __future__ import annotations

import hero_schema as HS

from . import items as I
from .common import title_lines
from .split_engine import MOTION

STYLE = "motion-editorial"
HERO_COMPONENTS = ["label-pill", "checklist-tick", "odometer", "typer", "before-after", "comment-cta", "stepper"]
MAX_W = 940
CAPTION_BAND = 150   # caption word sits clear of the speaker card's edge and shadow (style default 128)
LEAD = 0.25   # seconds after the cut that the stage type is in


def _size(text: str, lo: int = 120, hi: int = 300) -> int:
    """Font size that fills about the stage width on one line (kinetic data-fit only shrinks)."""
    return int(min(hi, max(lo, MAX_W / (0.56 * max(1, len(text))))))


def kinetic_word(text: str, at, hero: bool) -> dict:
    """One kinetic line per text line (a long phrase sets on 2 balanced lines, words verbatim). The type is on the
    stage right after the cut (never an empty stage); the spoken word lands as a highlighter wipe behind its line."""
    parts = I.two_lines(text).split("\n")
    size = min(_size(p) for p in parts)
    key = (at or "@")[1:]
    hit = next((i for i, p in enumerate(parts) if any(w.lower().startswith(key) for w in p.split())), len(parts) - 1)
    lines = [{"text": p, "font": "sans", "size": size, "color": "accent" if hero else "ink", "at": round(LEAD + 0.18 * i, 2),
              "enter": "slam" if hero and i == 0 else "rise", **({"mark": at} if at and i == hit else {})}
             for i, p in enumerate(parts)]
    return {"insert": "kinetic", "args": {"lines": lines, "max_w": MAX_W, "float": 0, "gap": 10}}


def kinetic_flow(shot: dict) -> dict:
    left, right = shot["left"], shot["right"]
    lines = [{"text": left, "font": "serif", "size": _size(left, 100, 190), "color": "accent", "at": LEAD},
             {"text": shot["arrow"], "font": "mono", "size": 60, "color": "soft", "at": LEAD + 0.2},
             {"text": right, "font": "sans", "size": _size(right, 100, 210), "color": "ink", "enter": "slam",
              "at": shot.get("anchor") or LEAD + 0.4}]
    return {"insert": "kinetic", "args": {"lines": lines, "max_w": MAX_W, "gap": 14, "float": 0}}


def top_for(shot: dict, line: str):
    k, at = shot["kind"], shot.get("anchor")
    if k == "none":
        return "full", None
    if k == "hero":
        hid = shot["hero_id"]
        if "card" in HS.HEROES[hid]["layouts"]:
            return "card", I.hero(hid, "cream", **{**shot["args"], "tone": "cream"})
        return "full", I.hero(hid, "dark", **shot["args"])
    if k == "word":
        return "card", kinetic_word(shot["text"], at, shot.get("hero", False))
    if k == "list":
        rows = [{"text": t, "at": LEAD if i == 0 else a} for i, (t, a) in enumerate(zip(shot["items"], shot["ticks"]))]
        return "card", {"insert": "cred_stack", "args": {"items": rows}}
    if k == "stat":
        return "card", I.odometer(shot)
    if k == "typer":
        return "card", I.typer(shot)
    if k == "flow":
        return "card", kinetic_flow(shot)
    if k == "cta":
        return "card", I.comment(shot, line)
    if k == "phone":
        return "full", I.phone(shot)
    raise ValueError(f"motion-editorial: no mapping for shot kind {k!r}")


def rows_and_beats(shots: list, lines: dict, title: str, wins: dict | None = None):
    rows = []
    for sid, shot in shots:
        mode, top = top_for(shot, lines[sid])
        rows.append({"id": sid, "mode": mode, "top": top})
    return rows, []


def project_patch(pj: dict, plan: dict, beats: list, first_seg_end: float | None = None) -> dict:
    l1, l2 = title_lines(plan.get("title", ""))
    hook = {"l1": l1, "l2": l2, "category": (pj.get("hook") or {}).get("category", "plan")}
    overlays = []
    if l1:
        overlays.append({"insert": "title_card", "from": 0.0, "until": first_seg_end,
                         "args": {"l1": l1, "l2": l2}})
    return {"style": STYLE, "motion": dict(MOTION), "hook": hook, "beats": beats, "overlays": overlays,
            "captions": {"mode": "word", "strip_punct": True, "accent": []},   # ink words: accent-colour words
                                                                              # measured 2.4:1 on the paper stage
            "card": {"caption_band": CAPTION_BAND}}
