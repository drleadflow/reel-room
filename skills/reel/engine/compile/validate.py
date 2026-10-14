"""Validators for the plan the compiler reads. Every error names the beat; all errors are reported at once."""
from __future__ import annotations

import plan_schema as PS

from .common import EM_DASH, CompileError

COMPONENTS = list(PS.COMPONENTS) + ["custom"]


def _anchor_ok(word, line) -> bool:
    return str(word or "").strip(".,!?;:'\"").lower() in PS.words_of(line)


def check_hero(b: dict, line: str) -> str | None:
    if b.get("component") != "custom":
        return "a hero beat must have component 'custom'"
    idea = b.get("visual_intent")
    if not isinstance(idea, str) or len(idea.strip()) < 20:
        return "hero beat needs its idea in visual_intent (20+ chars)"
    if not _anchor_ok(b.get("anchor_word"), line):
        return f"hero anchor_word {b.get('anchor_word')!r} is not in the line"
    return None


def check_plain(b: dict, line: str, context: str) -> str | None:
    comp = b.get("component")
    if comp not in COMPONENTS or comp == "custom":
        return f"bad component {comp!r}; use one of {PS.COMPONENTS}"
    text = b.get("on_screen_text") or ""
    if not isinstance(text, str):
        return "on_screen_text must be a string"
    if len(text) > PS.MAX_TEXT:
        return f"on_screen_text over {PS.MAX_TEXT} chars: {text!r}"
    if EM_DASH in text:
        return f"on_screen_text {text!r} has an em dash"
    if comp != "none" and not _anchor_ok(b.get("anchor_word"), line):
        return f"anchor_word {b.get('anchor_word')!r} is not in the line"
    return PS.invented(text, f"{line} {context}") if text else None


def check_beat(b: dict, line: str, context: str = "") -> str | None:
    """None when the beat is usable, else the problem (without the beat id)."""
    if str(b.get("line", "")).strip() != line.strip():
        return "line text differs from edl.json (the edit changed after planning): re-run plan_fast.py"
    if b.get("style") not in PS.STYLES:
        return f"bad style {b.get('style')!r}"
    return check_hero(b, line) if b.get("hero") else check_plain(b, line, context)


def edl_lines(edl: list) -> dict:
    return {e["id"]: str(e.get("line", "")).strip() for e in edl if e.get("id") and str(e.get("line", "")).strip()}


def _coverage(beats: list, lines: dict) -> list:
    ids = [b.get("id") for b in beats]
    errs = [f"beat {i}: not a segment in edl.json" for i in ids if i not in lines]
    errs += [f"segment {i}: has no beat in the plan (re-run plan_fast.py)" for i in lines if i not in ids]
    if not errs and ids != [i for i in lines if i in ids]:
        errs.append("plan beats are not in edl.json order")
    return errs


def check_plan(plan: dict, edl: list) -> None:
    """Raise CompileError listing every problem; return quietly when the plan can be compiled."""
    errs = []
    title_err = PS._text_ok(plan.get("title", ""), PS.MAX_TITLE)
    if title_err:
        errs.append("title: " + title_err)
    beats = plan.get("beats")
    if not isinstance(beats, list) or not beats:
        raise CompileError("plan has no beats")
    lines = edl_lines(edl)
    errs += _coverage(beats, lines)
    ids = list(lines)
    for b in beats:
        lid = b.get("id")
        if lid not in lines:
            continue
        i = ids.index(lid)
        context = " ".join(lines[j] for j in ids[max(0, i - 1):i + 2] if j != lid)
        err = check_beat(b, lines[lid], context)
        if err:
            errs.append(f"beat {lid}: {err}")
    if errs:
        raise CompileError("plan check failed:\n  " + "\n  ".join(errs))
