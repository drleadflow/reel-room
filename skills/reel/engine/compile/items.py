"""Insert items shared by the split-engine adapters (kit pieces + word_card). Each returns one edl `top` item.

Kit chrome that would put words on screen nobody said is switched off (typer labels, DM boilerplate), so the only
readable text is the plan's on-screen text or the speaker's own words.
"""
from __future__ import annotations

import re

from .common import title_lines


def kit(comp: str, **args) -> dict:
    return {"insert": "kit", "args": {"comp": comp, **{k: v for k, v in args.items() if v is not None}}}


LONG = 16   # chars: a longer phrase sets on 2 balanced lines (bigger type); the words stay verbatim


def two_lines(text: str) -> str:
    if "\n" in text or len(text) <= LONG or len(text.split()) < 3:
        return text
    return "\n".join(title_lines(text))


def word_card(text: str, at, hero: bool = False) -> dict:
    return {"insert": "word_card", "args": {"text": two_lines(text), "at": at, "hero": hero}}


def odometer(shot: dict) -> dict:
    """'100%' / '$39' / '7.5x' -> a kit odometer that rolls onto the spoken number (prefix / suffix kept verbatim)."""
    m = re.match(r"^([$\u00a3\u20ac]?)(\d+(?:[.,]\d+)?)\s?(.*)$", shot["value"])
    pre, num, suf = m.group(1), m.group(2), m.group(3)
    num = num.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", num) else num.replace(",", ".")
    dec = len(num.split(".")[1]) if "." in num else 0
    return kit("odometer", value=float(num), decimals=dec, prefix=pre, suffix=suf, at=0.0, land=shot.get("anchor"),
               label=shot.get("label") or None, size=260)


def flow_card(shot: dict, hero: bool = False) -> dict:
    """'A -> B' as one big two-line card, words and arrow verbatim."""
    return word_card(f"{shot['left']}\n{shot['arrow']} {shot['right']}", shot.get("anchor"), hero)


PANEL_MID = 580       # centre of the split panel's safe band (y 230-930): kit pieces sit there, not at the top edge


def typer(shot: dict) -> dict:
    return kit("typer", text=shot["text"], at=0.0, type_at=shot.get("anchor"), labels=["", "", ""], w=960,
               y=PANEL_MID - 74)


def checklist(shot: dict) -> dict:
    h = 98 * len(shot["items"]) + 70
    return kit("checklist-tick", items=shot["items"], ticks=shot["ticks"], at=0.0, w=900, y=round(PANEL_MID - h / 2))


def _after_keyword(line: str, keyword: str) -> str | None:
    """The speaker's own words after the keyword ('... the word EDIT down below and I'll share it' -> "I'll share
    it"), used as the DM text so the DM never shows invented copy. None when nothing short enough follows."""
    m = re.search(re.escape(keyword) + r"\b(.*)$", line, re.I)
    tail = (m.group(1) if m else "").strip(" ,.!?")
    tail = re.split(r"\band\b", tail, maxsplit=1)[-1].strip(" ,.!?") if " and " in f" {tail} " else tail
    return tail[:1].upper() + tail[1:] if tail and len(tail) <= 28 else None


def keyword_of(text: str, anchor: str | None) -> str:
    """The keyword to type: the text itself when it is one word, else its anchor word as written in the text
    ('comment the word EDIT' with anchor '@edit' -> 'EDIT')."""
    words = text.split()
    if len(words) == 1 or not anchor:
        return text
    return next((w.strip(".,!?\"'") for w in words if w.strip(".,!?\"'").lower() == anchor[1:]), text)


def comment(shot: dict, line: str) -> dict:
    kw = keyword_of(shot["text"], shot.get("anchor"))
    dm = _after_keyword(line, kw) or kw
    return kit("comment-cta", keyword=kw, at=0.0, type_at=shot.get("anchor"), dm_text=dm, link_text=kw,
               link_sub=" ", w=900, y=PANEL_MID - 250)


def phone(shot: dict) -> dict:
    return kit("phone-frame", at=0.2, title=shot.get("text") or None, chrome="app", scale=0.52, cy=980)


# ---------------------------------------------------------------------------------------------- rich top slot
def hero(hid: str, default_tone: str | None, **args) -> dict:
    """A library hero (templates/kit/heroes_*.py) through kit_insert.hero (layout, area, face filled at compose)."""
    a = {k: v for k, v in args.items() if v is not None}
    if default_tone and "tone" not in a:
        a["tone"] = default_tone
    return {"insert": "hero", "args": {"comp": hid, **a}}


def ground(tone: str) -> dict:
    """The colour-set ground for a split panel under a kit piece (no empty cream panel)."""
    return {"insert": "ground", "args": {"tone": tone}}


def title_stamp(text: str, at, tone: str, sub: str | None = None, neq: bool = False) -> dict:
    """One big phrase, verbatim, as a huge serif headline stamped on its word (replaces the small word card)."""
    return hero("title-stamp", tone, text=text, sub=sub, neq=neq or None, at=0.0, land=at)


def money(shot: dict, tone: str) -> dict:
    """'100%' / '$39' / '7.5x' -> money-counter: the number rolls and slams on its word, the rest as its label."""
    m = re.match(r"^([$£€]?)(\d+(?:[.,]\d+)?)\s?(.*)$", shot["value"])
    pre, num, suf = m.group(1), m.group(2), m.group(3)
    num = num.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", num) else num.replace(",", ".")
    return hero("money-counter", tone, steps=[[num, shot.get("anchor")]], prefix=pre or None, unit=suf or None,
                label=shot.get("label") or None, bars=False, at=0.0)
