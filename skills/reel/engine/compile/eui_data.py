"""editorial-ui data heroes and substitutions (compile/editorial_ui.py calls route() before it builds the beats).

  title-stamp    -> a colour-set headline (the style's own huge serif behind the head), counted in the 4 set
                    headlines; past the cap it becomes the everyday ed-headline card
  money-counter  -> its own colour-set scene (cut-out on a plain plate, punch-in 1.0) with the counter in the upper
  evidence-hero     third, above the head (never over the face); the optional rows (kicker, label, bars, stat) are
                    dropped until it fits the band the face leaves. evidence-hero citations must pass the validator
                    against work/sources.txt
  no room / too short / cap / invalid -> the closest allowed treatment (ed-number from the counter's last step or the
                    evidence stat, a SOURCE status pill from the citation, else the anchor word), always with a note
Nothing a style cannot draw is dropped silently: every substitution is a compile note.
"""
from __future__ import annotations

from pathlib import Path

import hero_schema as HS

DATA = ("money-counter", "evidence-hero")
STAMP = "title-stamp"
BAND_TOP = 244                 # editorial band.top (first card row, under the Reels safe top)
CAM_PAD, FACE_PAD = 40, 0.18    # kitcards.band: camera push + QA face pad (share of the face height)
BROW_UP, CHIN_DOWN = 0.5, 0.8   # templates/editorial-ui/plan.py face box around the detector centre
EST_MARGIN = 30                # px: the per-frame track's highest brow sits a little above the median
NUM_MIN = 150                  # px: the counter's number never smaller than this
CHART_MIN = 220                # px: the evidence chart's plot never shorter than this
DATA_PAD = 0.3                 # s on top of the hero's min_secs (its cut must hold it)


def band_height(face: dict | None, zoom: float = 1.0) -> float:
    """Height of the band above the head (set scene at `zoom`), from work/facepos.json {cx, cy, h} (aroll px)."""
    if not face:
        return 0.0
    h = float(face["h"]) * zoom
    brow = float(face["cy"]) - BROW_UP * h - EST_MARGIN
    return brow - FACE_PAD * (BROW_UP + CHIN_DOWN) * h - CAM_PAD - BAND_TOP


def _counter_fixed(args: dict) -> int:
    steps = len(args.get("steps") or [])
    bars = args.get("bars", True) and steps > 1
    return (76 if args.get("kicker") else 0) + 40 + (84 * steps if bars else 0) + (80 if args.get("label") else 0) + 20


def fit_counter(args: dict, band: float) -> dict | None:
    """money-counter args that fit the band (drops kicker, then label, then bars), else None."""
    for drop in ((), ("kicker",), ("kicker", "label"), ("kicker", "label", "bars")):
        a = {k: v for k, v in args.items() if k not in drop}
        if "bars" in drop:
            a["bars"] = False
        if band - _counter_fixed(a) >= 0.9 * NUM_MIN:
            return a
    return None


def _evidence_fixed(args: dict) -> int:
    return 10 + (46 if args.get("kicker") else 0) + (180 if args.get("stat") else 0) + 70 + 175


def fit_evidence(args: dict, band: float) -> dict | None:
    """evidence-hero args that fit the band (drops kicker, then the stat row), else None."""
    for drop in ((), ("kicker",), ("kicker", "stat", "stat_label")):
        a = {k: v for k, v in args.items() if k not in drop}
        if band - _evidence_fixed(a) >= CHART_MIN:
            return a
    return None


def sources_txt(proj: Path) -> str:
    p = Path(proj) / "work" / "sources.txt"
    return p.read_text(errors="ignore") if p.exists() else ""


# ---------------------------------------------------------------------------------------------- substitutions
def counter_card(s: dict) -> dict | None:
    """money-counter -> ed-number shot on its last spoken step (prefix + value, unit as the context)."""
    steps = s["args"].get("steps") or []
    if not steps:
        return None
    v, at = steps[-1][0], steps[-1][1]
    label = s["args"].get("unit") or s["args"].get("label") or ""
    return {**_base(s), "kind": "stat", "value": f"{s['args'].get('prefix', '')}{v}", "label": label, "anchor": at}


def evidence_card(s: dict) -> dict | None:
    """evidence-hero -> ed-number on its stat, else a SOURCE status pill with the citation."""
    a = s["args"]
    if a.get("stat"):
        return {**_base(s), "kind": "stat", "value": a["stat"], "label": a.get("stat_label") or "",
                "anchor": a.get("stamp") or s.get("anchor")}
    if a.get("citation"):
        return {**_base(s), "kind": "source", "text": a["citation"], "anchor": a.get("draw") or s.get("anchor")}
    return None


def word_of(s: dict) -> dict:
    """The anchor word as a plain word shot (always a spoken word, so it validates)."""
    return {**_base(s), "kind": "word", "text": (s.get("anchor") or "@")[1:] or s["comp"]}


def stamp_word(s: dict) -> dict:
    a = s["args"]
    text = a.get("text") or (s.get("anchor") or "@")[1:]
    return {**_base(s), "kind": "word", "text": f"{text} | {a['sub']}" if a.get("sub") else text, "stamp": True,
            "anchor": a.get("land") or s.get("anchor")}


def _base(s: dict) -> dict:
    return {k: s[k] for k in ("section", "purpose", "comp") if k in s} | {"hero": True}


def _substitute(sid: str, s: dict, why: str, notes: list) -> dict:
    sub = (counter_card(s) if s["hero_id"] == "money-counter" else evidence_card(s)) or word_of(s)
    what = {"stat": "ed-number", "source": "SOURCE status pill", "word": "everyday word card"}[sub["kind"]]
    notes.append(f"beat {sid}: {s['hero_id']} {why}, shown as {what}")
    return sub


def _data_shot(sid: str, s: dict, ctx: dict, notes: list) -> dict:
    """A data hero kept on its own colour set (fitted args), or its substitute."""
    hid, (t0, t1) = s["hero_id"], ctx["wins"][sid]
    if t1 - t0 < HS.HEROES[hid]["min_secs"] + DATA_PAD:
        return _substitute(sid, s, f"needs {HS.HEROES[hid]['min_secs'] + DATA_PAD:.1f} s, its cut is {t1 - t0:.1f} s",
                           notes)
    if hid == "evidence-hero":
        err = HS.validate(hid, {k: v for k, v in s["args"].items() if k not in HS.COMPILER_KEYS},
                          ctx["lines"].get(sid, ""), ctx["context"].get(sid, ""), ctx["sources"])
        if err:
            return _substitute(sid, s, f"citation / data not valid against work/sources.txt ({err})", notes)
    band = band_height(ctx["facepos"].get(sid), 1.0)
    args = (fit_counter if hid == "money-counter" else fit_evidence)(s["args"], band)
    if args is None:
        return _substitute(sid, s, f"no room above the head ({max(0, band):.0f} px band)", notes)
    if args != s["args"]:
        notes.append(f"beat {sid}: {hid} trimmed to fit the {band:.0f} px band above the head "
                     f"(dropped {', '.join(sorted(set(s['args']) - set(args))) or 'bars'})")
    return {**s, "args": args, "data_set": True}


def route(shots: list, ctx: dict, allowed: tuple) -> tuple:
    """(shots, notes): title-stamps -> set headlines, data heroes -> own colour set or a logged substitute, any other
    hero the style cannot draw -> its anchor word, with a note. ctx: wins, lines, context, facepos, sources."""
    out, notes = [], []
    for sid, s in shots:
        if s.get("kind") != "hero":
            out.append((sid, s))
            continue
        hid = s["hero_id"]
        if hid == STAMP:
            out.append((sid, stamp_word(s)))
            notes.append(f"beat {sid}: title-stamp shown as a colour-set headline (editorial-ui's serif stamp)")
        elif hid in DATA:
            out.append((sid, _data_shot(sid, s, ctx, notes)))
        elif hid not in allowed:
            out.append((sid, word_of(s)))
            notes.append(f"beat {sid}: {hid} is not drawn by editorial-ui, shown as an everyday word card")
        else:
            out.append((sid, s))
    return out, notes


def planner_notes(beats: list, picked: dict, allowed: tuple) -> list:
    """The planner's suggested library hero, when the compiler used something else, says so (never silent)."""
    notes = []
    for b in beats:
        want = b.get("library")
        got = (picked.get(b["id"]) or {}).get("hero", "none")
        if want and want != got:
            why = "not in this style's library" if want not in allowed else "the model picked another fill"
            notes.append(f"beat {b['id']}: planner asked for {want} ({why}), used {got}")
    return notes
