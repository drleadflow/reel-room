"""Everyday beats for the adapters: word / list / stat / flow shots -> a editorial-style editorial treatment from the kit
(templates/kit/beats_editorial.py) instead of the plain white pill card.

  word  -> ed-headline (serif headline + italic sub-line, the sub = the speaker's next words) or ed-kicker (the
           speaker's words just before the phrase as a mono kicker over the headline)
  list  -> ed-checklist (rows tick on their words)          stat -> ed-number (number slams, context line above)
  flow  -> ed-contrast ('A' struck on its word, 'B' lands in italic accent)
Every fill passes engine/beat_schema.py (spoken words and numbers only, anchors in the line); a fill that fails
returns None and the adapter keeps its previous item. Kickers and sub-lines are copied verbatim from the line.
"""
from __future__ import annotations

import re

import beat_schema as BS

from .common import norm

KICK_MAX, SUB_MAX = 26, 26


def item(bid: str, args: dict, tone: str) -> dict:
    """Split-engine insert (compiled projects): {"insert": "beat", "args": {"comp", ...}}."""
    return {"insert": "beat", "args": {"comp": bid, **{k: v for k, v in args.items() if v is not None}, "tone": tone}}


def _tokens(line: str) -> list:
    return [w for w in re.findall(r"\S+", str(line))]


def _find(phrase: str, toks: list):
    """(start, end) token index of `phrase` inside the line tokens (normalised), else None."""
    want = [norm(w) for w in str(phrase).split() if norm(w)]
    have = [norm(t) for t in toks]
    for i in range(len(have) - len(want) + 1):
        if want and have[i:i + len(want)] == want:
            return i, i + len(want)
    return None


def _clean(words: list) -> str:
    return " ".join(words).strip(" ,.;:!?\"'")


def kicker_of(text: str, line: str) -> str | None:
    """Up to 3 spoken words right before the phrase (same clause), when they read as a lead-in."""
    toks = _tokens(line)
    pos = _find(text, toks)
    if not pos or pos[0] < 2:
        return None
    before = toks[max(0, pos[0] - 3):pos[0]]
    while before and re.search(r"[.,;:!?]$", before[0]):
        before = before[1:]
    k = _clean(before)
    return k if len(k.split()) >= 2 and len(k) <= KICK_MAX and any(len(norm(w)) > 3 for w in before) else None


def sub_of(text: str, line: str) -> str | None:
    """The spoken words right after the phrase up to the clause end (2 to 5 words), as the italic sub-line."""
    toks = _tokens(line)
    pos = _find(text, toks)
    if not pos or re.search(r"[.,;:!?]$", toks[pos[1] - 1]):
        return None
    after = []
    for t in toks[pos[1]:pos[1] + 5]:
        after.append(t)
        if re.search(r"[.,;:!?]$", t):
            break
    s = _clean(after)
    return s if 2 <= len(s.split()) <= 5 and len(s) <= SUB_MAX else None


def _ok(bid: str, args: dict, line: str, context: str):
    return args if BS.validate(bid, args, line, context) is None else None


def _word_options(shot: dict, line: str) -> list:
    """Candidate treatments for one phrase, best first: a spoken number slams; 'A | B' or the next spoken words as
    an italic sub-line; the words before it as a kicker; the bare headline."""
    text, at = shot["text"], shot.get("anchor")
    out = []
    if re.search(r"\d", text):
        value = re.search(r"[$£€]?\d+(?:[.,]\d+)?\s?[%xX+]?", text).group(0).strip()
        rest = text.replace(value, "").strip(" :-|")
        out.append(("ed-number", {"value": value, "context": rest or kicker_of(value, line), "land": at}))
    if "|" in text:
        a, b = (x.strip() for x in text.split("|", 1))
        out.append(("ed-headline", {"text": a, "sub": b, "land": at}))
        text = a
    if sub_of(text, line):
        out.append(("ed-headline", {"text": text, "sub": sub_of(text, line), "land": at}))
    if kicker_of(text, line):
        out.append(("ed-kicker", {"kicker": kicker_of(text, line), "text": text, "land": at}))
    out.append(("ed-headline", {"text": text, "land": at}))
    return out


def word(shot: dict, line: str, context: str = "", avoid: str | None = None):
    """(beat id, args) for one big phrase, or None. avoid: the previous card's beat id (no two alike in a row)."""
    valid = [(bid, a) for bid, a in _word_options(shot, line) if _ok(bid, a, line, context)]
    fresh = [v for v in valid if v[0] != avoid]
    return (fresh or valid or [None])[0]


def tick_anchors(items: list, line: str) -> list | None:
    """One '@word' per item: its first content word (not 'the', 'a', ...) that the line says, in spoken order."""
    import plan_schema as PS
    said, out = [norm(t) for t in _tokens(line)], []
    for it in items:
        words = [norm(w) for w in it.split() if norm(w) and norm(w) not in PS.STOP] or [norm(it.split()[0])]
        out.append(next((f"@{w}" for w in words if w in said), None))
    return out if all(out) else None


def checklist(shot: dict, line: str, context: str = ""):
    args = {"items": shot["items"], "ticks": tick_anchors(shot["items"], line)}
    args = _ok("ed-checklist", args, line, context)
    return ("ed-checklist", args) if args else None


def number(shot: dict, line: str, context: str = ""):
    ctx = (shot.get("label") or "").strip() or kicker_of(shot["value"], line)
    args = _ok("ed-number", {"value": shot["value"], "context": ctx or None, "land": shot.get("anchor")}, line, context)
    if args is None and ctx:
        args = _ok("ed-number", {"value": shot["value"], "land": shot.get("anchor")}, line, context)
    return ("ed-number", args) if args else None


def contrast(shot: dict, line: str, context: str = ""):
    """Strike 'A' when the speaker reaches 'B' (B's first spoken word), B lands on the plan's anchor."""
    toks = _tokens(line)
    pos = _find(shot["right"].split()[0], toks)
    strike = ("@" + norm(toks[pos[0]])) if pos else None
    arrow = "→" if shot.get("arrow", "→").strip() in ("→", "->", "=>") else shot["arrow"].strip()
    a_pos = _find(shot["left"].split()[0], toks)
    a_at = ("@" + norm(toks[a_pos[0]])) if a_pos else None
    args = {"left": shot["left"], "right": shot["right"], "arrow": arrow, "a_at": a_at, "strike_at": strike,
            "land": strike or shot.get("anchor")}      # B lands as it is said (the plan's anchor may come before A)
    args = _ok("ed-contrast", args, line, context)
    return ("ed-contrast", args) if args else None


BY_KIND = {"word": word, "list": checklist, "stat": number, "flow": contrast}


def build(shot: dict, line: str, context: str = "", avoid: str | None = None):
    """(beat id, args) for a word / list / stat / flow shot, or None (keep the adapter's previous item). avoid: the
    previous card's beat id; a phrase picks another treatment so no two cards in a row look alike."""
    fn = BY_KIND.get(shot.get("kind"))
    if not fn:
        return None
    return fn(shot, line, context, avoid) if fn is word else fn(shot, line, context)
