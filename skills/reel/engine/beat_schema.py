"""Typed contracts for the everyday editorial beats (templates/kit/beats_editorial.py: ed-headline, ed-number,
ed-checklist, ed-contrast, ed-kicker) and the validator every compiled fill passes before it reaches a project.

Same rules as hero_schema.py: on-screen words and numbers come from the spoken line or its neighbours
(plan_schema.invented), no em dashes, anchors are words of THIS line, colour sets are brand sets only. Pure functions.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import hero_schema as HS
import plan_schema as PS

KIT = Path(__file__).resolve().parent.parent / "templates" / "kit"
if str(KIT) not in sys.path:
    sys.path.append(str(KIT))
import beats_editorial as _B  # noqa: E402

BEATS = _B.BEATS
LAYOUT_KEYS = ("layout", "area", "z")      # the adapter places a beat; never part of the spoken contract


def required(bid: str) -> list:
    sig = inspect.signature(BEATS[bid]["fn"])
    return [p.name for p in list(sig.parameters.values())[1:] if p.default is inspect._empty]


def validate(bid: str, args: dict, line: str, context: str = "") -> str | None:
    """None when `args` is a usable fill of beat `bid` for this line, else the first problem."""
    if bid not in BEATS:
        return f"unknown beat {bid!r}; use one of {sorted(BEATS)}"
    if not isinstance(args, dict):
        return "args must be an object"
    fields = BEATS[bid]["fields"]
    extra = [k for k in args if k not in fields and k not in LAYOUT_KEYS]
    if extra:
        return f"unknown field(s) {extra} for {bid}; allowed: {sorted(fields)}"
    missing = [k for k in required(bid) if args.get(k) in (None, "", [])]
    if missing:
        return f"{bid} needs {missing}"
    words = PS.words_of(line)
    spoken = f"{line} {context}"
    for k, v in args.items():
        if k in LAYOUT_KEYS or v is None:
            continue
        t, o = fields[k]
        if t == "anchor" and isinstance(v, (int, float)):
            continue
        err = HS._check_field(t, o, v, words, spoken, "")
        if err:
            return f"{k}: {err}"
    return None


def catalog_text() -> str:
    return "\n".join(f"- {bid}: {c['what']}" for bid, c in BEATS.items())
