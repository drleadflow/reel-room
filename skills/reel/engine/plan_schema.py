"""Schemas and validators for the fast planner. Pure functions: each returns None when valid,
or a short error string the model gets back on retry.
"""
from __future__ import annotations

import re

STYLES = ["editorial-ui", "clean-talk", "motion-editorial", "split-deck", "list-stack",
          "floating-cards", "carousel-slideup", "desk-demo"]
PURPOSES = ["hook", "promise", "proof", "explain", "transition", "cta"]
COMPONENTS = ["typer", "checklist-tick", "progress-bar", "odometer", "label-pill", "receipt", "comment-cta",
              "stepper", "annotation-arrow", "phone-frame", "before-after", "spotlight", "head-bubble",
              "behind-head-word", "none"]
MAX_TEXT = 28
MAX_TITLE = 40
MAX_HEROES = 5      # hero moments per reel (library heroes make more of them affordable)
MIN_OVERLAP = 0.5  # share of on-screen content words that must come from the spoken lines
STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "your", "you", "i", "my", "with"}
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
EM_DASH = "—"


def words_of(line: str) -> set:
    return {w.strip(".,!?;:'\"()").lower() for w in line.split() if w.strip(".,!?;:'\"()")}


def _text_ok(text, limit) -> str | None:
    if not isinstance(text, str):
        return "text must be a string"
    if len(text) > limit:
        return f"text over {limit} chars: {text!r}"
    if EM_DASH in text:
        return "no em dashes in on-screen text"
    return None


def check_sections(sections, ids) -> str | None:
    """Sections must cover every line id exactly once, in order, as contiguous runs."""
    if not isinstance(sections, list) or not sections:
        return "sections must be a non-empty list"
    flat = []
    for s in sections:
        if s.get("style") not in STYLES:
            return f"bad style {s.get('style')!r}; use one of {STYLES}"
        if s.get("purpose") not in PURPOSES:
            return f"bad purpose {s.get('purpose')!r}; use one of {PURPOSES}"
        if not s.get("line_ids"):
            return "every section needs line_ids"
        flat.extend(s["line_ids"])
    if flat != list(ids):
        return "sections must list every line id once, in transcript order"
    return None


def check_heroes(heroes, lines: dict) -> str | None:
    if not isinstance(heroes, list) or not 1 <= len(heroes) <= MAX_HEROES:
        return f"hero_moments must be a list of 1 to {MAX_HEROES}"
    for h in heroes:
        lid = h.get("line_id")
        if lid not in lines:
            return f"hero line_id {lid!r} is not a real id"
        if str(h.get("anchor_word", "")).strip(".,!?").lower() not in words_of(lines[lid]):
            return f"hero anchor_word {h.get('anchor_word')!r} is not in line {lid}"
        if not isinstance(h.get("idea"), str) or len(h["idea"]) < 20:
            return "each hero needs a concrete idea (20+ chars)"
        if h.get("library") and h["library"] not in hero_ids():
            return f"hero library {h['library']!r} is not a library id; use one of {hero_ids()} or omit it"
    return None


def hero_ids() -> list:
    """Hero library ids (templates/kit/heroes_*.py), loaded lazily so the planner works without the kit on path."""
    try:
        import hero_schema
        return sorted(hero_schema.HEROES)
    except ImportError:
        return []


def check_reel_plan(plan: dict, lines: dict) -> str | None:
    """Validate the Claude pass: title, hook, sections and hero moments."""
    err = _text_ok(plan.get("title", ""), MAX_TITLE)
    if err:
        return "title: " + err
    if plan.get("hook_id") not in lines:
        return f"hook_id {plan.get('hook_id')!r} is not a real line id"
    return check_sections(plan.get("sections"), list(lines)) or check_heroes(plan.get("hero_moments"), lines)


def invented(text: str, spoken: str) -> str | None:
    """Reject on-screen text that adds numbers or words the speaker never said nearby."""
    said = set(_NUM.findall(spoken))            # whole numbers only: '0' is not said because '100%' was
    for n in _NUM.findall(text):
        if n not in said and n.replace(",", "") not in {x.replace(",", "") for x in said}:
            return f"number {n!r} was never said; use only numbers from the lines"
    content = [w for w in words_of(text) if w not in STOP and not _NUM.fullmatch(w)]
    if content:
        heard = words_of(spoken)
        share = sum(1 for w in content if w in heard or w.rstrip("s") in heard) / len(content)
        if share < MIN_OVERLAP:
            return f"on_screen_text {text!r} invents words; reuse the speaker's own words"
    return None


def check_beat(line: str, context: str = ""):
    """Validator factory for one Jev beat decision. `context` = neighbouring lines the text may also quote."""
    words = words_of(line)
    spoken = f"{line} {context}"

    def check(d: dict) -> str | None:
        if d.get("component") not in COMPONENTS:
            return f"bad component {d.get('component')!r}; use one of {COMPONENTS}"
        err = _text_ok(d.get("on_screen_text", ""), MAX_TEXT)
        if err:
            return err
        if d["component"] != "none" and str(d.get("anchor_word", "")).strip(".,!?").lower() not in words:
            return f"anchor_word {d.get('anchor_word')!r} must be copied from the line"
        return invented(d.get("on_screen_text", ""), spoken)
    return check


def check_vote(ids) -> callable:
    def check(d: dict) -> str | None:
        return None if d.get("best_id") in ids else f"best_id {d.get('best_id')!r} is not a real id"
    return check
