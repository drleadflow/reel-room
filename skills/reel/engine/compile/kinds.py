"""Plan component + on-screen text -> one neutral shot kind every style adapter understands.

  none   caption only                      word   one big phrase (label, behind-head word without a cut-out, ...)
  list   2+ items that tick on their words stat   a number that lands on its word (+ the rest as its label)
  typer  text typed like a prompt          flow   'A -> B' (before / after)
  cta    a keyword to comment              phone  the speaker shrinks into a phone (optional title)
  hero   a library hero (heroes_*.py) with its validated, filled contract (beat["hero_lib"], beat["hero_args"])
Every shot also carries its plan section (colour sets change per section).
On-screen text is never rewritten: kinds only split it (lines, commas, a number, an arrow).
"""
from __future__ import annotations

from .common import anchor_for, arrow_split, first_anchor, norm, number_in, split_items

LISTISH = {"checklist-tick", "receipt", "stepper"}
STATISH = {"odometer", "progress-bar"}


def _item_anchors(items: list, in_seg: list) -> list:
    """One anchor per list item: its first spoken word inside the segment, else None (default spacing)."""
    out = []
    for it in items:
        toks = [t for t in (norm(x) for x in it.split()) if len(t) > 2] or [norm(it.split()[0])]
        out.append(next((a for a in (anchor_for(t, in_seg) for t in toks) if a), None))
    return out


def _by_text(comp: str, text: str) -> dict:
    if comp == "typer":
        return {"kind": "typer", "text": text}
    if comp == "comment-cta":
        return {"kind": "cta", "text": text}
    if comp == "phone-frame":
        return {"kind": "phone", "text": text}
    if comp in LISTISH:
        items = split_items(text)
        return {"kind": "list", "items": items} if len(items) >= 2 else {"kind": "word", "text": text}
    if comp in STATISH:
        value, rest = number_in(text)
        return {"kind": "stat", "value": value, "label": rest} if value else {"kind": "word", "text": text}
    if comp == "before-after":
        parts = arrow_split(text)
        return {"kind": "flow", "left": parts[0], "arrow": parts[1], "right": parts[2]} if parts else \
            {"kind": "word", "text": text}
    return {"kind": "word", "text": text}


def classify(beat: dict, in_seg: list) -> dict:
    """beat: a plan beat (heroes already resolved to a kit fallback). in_seg: the words spoken in its segment."""
    if beat.get("hero_lib"):
        return {"kind": "hero", "comp": beat["hero_lib"], "hero_id": beat["hero_lib"], "args": dict(beat["hero_args"]),
                "hero": True, "section": beat.get("section"), "purpose": beat.get("purpose"),
                "anchor": anchor_for(beat.get("anchor_word", ""), in_seg) or first_anchor(in_seg)}
    comp = beat.get("component", "none")
    text = str(beat.get("on_screen_text") or "").strip()
    hero = bool(beat.get("hero"))
    if comp == "none" or (not text and comp != "phone-frame"):
        return {"kind": "none", "comp": comp, "hero": hero, "dropped": comp != "none", "section": beat.get("section"),
                "purpose": beat.get("purpose")}
    shot = {**_by_text(comp, text), "comp": comp, "hero": hero, "section": beat.get("section"),
            "purpose": beat.get("purpose")}
    shot["anchor"] = anchor_for(beat.get("anchor_word", ""), in_seg) or first_anchor(in_seg)
    if shot["kind"] == "list":
        shot["ticks"] = _item_anchors(shot["items"], in_seg)
    return shot
