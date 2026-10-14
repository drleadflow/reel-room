"""split-deck adapter: graphics in the top panel, speaker under the seam, caption-only lines go full frame.

  none  -> full (caption only; back-to-back caption-only cuts alternate a punch-in so every cut reads)
  word  -> split + title-stamp (huge serif headline on its word; capped at 4, the rest and long phrases become the
           everyday ed-headline / ed-kicker, compile/everyday.py)        list  -> split + ed-checklist
  stat  -> split + ed-number (number slams, context line)             typer -> split + ground + kit typer
  flow  -> split + ed-contrast ('A' struck, 'B' lands in italic)      cta   -> split + ground + kit comment-cta
  phone -> full + kit phone-frame        hero -> the library hero (top slot, or full frame for frame heroes)
The top panel always carries a rich element on a colour-set ground that changes per plan section (rich.py); a
split-panel hero borrows the caption-only lines before it when its own line is too short (rich.extend_spans).
The hook title opens the reel as a title-stamp on the first segment; when the first line also has a graphic it
takes over the panel on its word (a project beat). No cut-out in this style, so behind-head words become stamps.
"""
from __future__ import annotations

import hero_schema as HS

from . import everyday as E
from . import items as I
from . import rich as R
from .split_engine import MOTION, hold_gap
from .common import title_lines

STYLE = "split-deck"
MOTION_EXTRA = {"transitions": {"per10s": 2.0, "moves": ["push"]}}   # calm: no zoom-blur transitions (judge: jarring)
HERO_COMPONENTS = ["label-pill", "checklist-tick", "odometer", "typer", "before-after", "comment-cta", "stepper"]


def _flow(shot: dict, tone: str) -> dict:
    sub = f"{shot['arrow']} {shot['right']}"
    if len(shot["left"]) <= 28 and len(sub) <= 28:
        return I.title_stamp(shot["left"], shot.get("anchor"), tone, sub=sub)
    return I.flow_card(shot, shot.get("hero", False))


def _everyday(shot: dict, line: str, tone: str, context: str, avoid: str | None = None):
    """The editorial-style everyday beat for word / list / stat / flow, or None when its fill does not validate."""
    got = E.build(shot, line, context, avoid)
    return E.item(got[0], got[1], tone) if got else None


def top_for(shot: dict, line: str, tone: str = "dark", context: str = "", avoid: str | None = None):
    """(mode, top item or None) for one shot. avoid: the previous everyday beat (no two alike in a row)."""
    k, at = shot["kind"], shot.get("anchor")
    if k in ("list", "stat", "flow") or (k == "word" and len(shot["text"].replace("|", " ")) > 28):
        ed = _everyday(shot, line, tone, context, avoid)
        if ed:
            return "split", ed
    if k == "none":
        return "full", None
    if k == "hero":
        hid = shot["hero_id"]
        args = dict(shot["args"])
        if hid != "word-stamp":
            args["at"] = 0.0                  # enter on the cut (never an empty panel); payoffs still land on words
        return HS.HEROES[hid]["split_mode"], I.hero(hid, tone, **args)
    if k == "word":
        text = shot["text"]
        if "|" in text:                       # 'A | B': a headline and its italic sub-line, words verbatim
            a, b = (x.strip() for x in text.split("|", 1))
            if a and b:
                return "split", I.title_stamp(a, at, tone, sub=b)
        return "split", (I.title_stamp(text, at, tone) if len(text) <= 28
                         else I.word_card(text, at, shot.get("hero", False)))
    if k == "list":
        return "split", [I.ground(tone), I.checklist(shot)]
    if k == "stat":
        return "split", I.money(shot, tone)
    if k == "typer":
        return "split", [I.ground(tone), I.typer(shot)]
    if k == "flow":
        return "split", _flow(shot, tone)
    if k == "cta":
        return "split", [I.ground(tone), I.comment(shot, line)]
    if k == "phone":
        return "full", I.phone(shot)
    raise ValueError(f"split-deck: no mapping for shot kind {k!r}")


def hook_card(title: str, tone: str = "dark") -> dict:
    l1, l2 = title_lines(title)
    if len(l1) <= 28 and len(l2) <= 28:
        return I.hero("title-stamp", tone, text=l1, sub=l2 or None, at=0.0, land=0.1, sub_at=0.45)
    return {"insert": "hook_card", "args": {"l1": l1, "l2": l2 or l1, "l2_at": 0.45, "line_at": 0.9}} if l2 else \
        {"insert": "word_card", "args": {"text": l1, "at": 0.1, "hero": True}}


def rows_and_beats(shots: list, lines: dict, title: str, wins: dict | None = None):
    """edl rows + project beats. shots: [(seg id, shot)] in edl order."""
    rows, beats, prev = [], [], None
    tones = R.section_tones(shots)
    ids = list(lines)
    for i, (sid, shot) in enumerate(shots):
        tone = R.tone_of(shot, tones)
        k = ids.index(sid) if sid in ids else 0
        ctx = " ".join(lines[j] for j in ids[max(0, k - 1):k + 2] if j != sid)
        mode, top = top_for(shot, lines[sid], tone, ctx, prev)
        prev = (top or {}).get("args", {}).get("comp", prev) if isinstance(top, dict) else prev
        if i == 0 and title:
            if top is not None and mode == "split" and shot.get("anchor"):
                beats.append({"at_word": shot["anchor"][1:], "seg": sid, "layout": "split", "items": top
                              if isinstance(top, list) else [top]})
            mode, top = "split", hook_card(title, tone)
        rows.append({"id": sid, "mode": mode, "top": top})
    sid_of = {id(sh): sid for sid, sh in shots}
    rows = R.cap_title_stamps(rows, shots, lambda sh, args: _calm(sh, args, lines.get(sid_of.get(id(sh)), "")))
    return R.extend_spans(rows, shots, wins), beats


def _calm(shot: dict, args: dict, line: str = ""):
    """A capped title-stamp becomes the calmer everyday editorial beat (ed-headline / ed-kicker) on the section's
    colour set; the old word card on a ground only when that fill does not validate."""
    tone = args.get("tone", "cream")
    text = args["text"] + (f" | {args['sub']}" if args.get("sub") else "")
    ed = _everyday({**shot, "kind": "word", "text": text, "anchor": args.get("land")}, line or text, tone, "")
    if ed:
        return ed
    text = args["text"] + (f"\n{args['sub']}" if args.get("sub") else "")
    return [I.ground(tone), I.word_card(text, args.get("land"), False)]


def project_patch(pj: dict, plan: dict, beats: list) -> dict:
    l1, l2 = title_lines(plan.get("title", ""))
    hook = {"l1": l1, "l2": l2, "category": (pj.get("hook") or {}).get("category", "plan")}
    return {"style": STYLE, "motion": dict(MOTION), "hook": hook, "beats": beats,
            "captions": {"mode": "pill", "max_words": 3, "hold_gap": hold_gap(pj)}}
