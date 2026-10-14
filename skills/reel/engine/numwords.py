"""Number readings for numcheck.py / numgate.py: digits and spoken number words -> canonical values. Pure functions.

  digits_in("$60 billion, 0.24 and 1,000")   -> ["60", "0.24", "1000"]     (what a screen shows)
  spoken_values("over seven, point two four") -> {"7", "0.24", ...}          (what a second transcript heard)
A scaled number ("sixty billion", "60 billion") reads as both its mantissa ("60") and its full value, so a caption
"$60 billion" and a transcript "sixty billion" agree, and "16 billion" never does.
"""
from __future__ import annotations

import re

DIGITS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d*\.\d+|\d+")
TOKEN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d*\.\d+|\d+|[A-Za-z]+")
ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
ONES["oh"] = 0
TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
SCALES = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


def canon(value) -> str | None:
    """'1,000' -> '1000', '07' -> '7', '0.240' -> '0.24', '.5' -> '0.5'; None when it is not a number."""
    s = str(value).replace(",", "").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    if f == int(f):
        return str(int(f))
    return f"{f:.6f}".rstrip("0").rstrip(".")


def digits_in(text: str) -> list:
    """Canonical values of the digit numbers in on-screen text, in order."""
    return [c for c in (canon(m) for m in DIGITS.findall(str(text or ""))) if c is not None]


def has_digits(text) -> bool:
    return bool(DIGITS.search(str(text or "")))


def _is_word_num(t: str) -> bool:
    return t in ONES or t in TENS or t == "hundred" or t in SCALES or t == "point"


def _group_value(toks: list) -> list:
    """Values for one run of number words ('sixty billion' -> ['60', '60000000000'])."""
    total, cur, dec, out_scaled = 0, 0, None, None
    for t in toks:
        if t == "point":
            dec = ""
        elif dec is not None and t in ONES:
            dec += str(ONES[t])
        elif t in ONES:
            cur += ONES[t]
        elif t in TENS:
            cur += TENS[t]
        elif t == "hundred":
            cur = max(1, cur) * 100
        elif t in SCALES:
            out_scaled = cur if out_scaled is None else out_scaled
            total += max(1, cur) * SCALES[t]
            cur = 0
    base = total + cur
    vals = [f"{base}.{dec}" if dec else str(base)]
    if out_scaled is not None:
        vals.append(str(out_scaled))
    return [c for c in (canon(v) for v in vals) if c is not None]


def _flush(run: list, out: set) -> None:
    if any(t in ONES or t in TENS for t in run):     # a lone scale word ('60 billion') is not a new number
        out.update(_group_value(run))


def spoken_values(text: str) -> set:
    """Every value a transcript says: digits ('7', '12', '0.24'), number words ('seven', 'point two four',
    'sixty billion'), a digit followed by a scale word ('60 billion' -> 60 and 60e9), ordinals (first..fifth)."""
    toks = [t.lower() for t in TOKEN.findall(str(text or ""))]
    out, run = set(), []
    for i, t in enumerate(toks):
        if t[0].isdigit() or t[0] == ".":
            _flush(run, out)
            run = []
            c = canon(t)
            if c is not None:
                out.add(c)
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if nxt in SCALES:
                    out.add(canon(float(c) * SCALES[nxt]))
            continue
        if _is_word_num(t) or (t == "and" and run and i + 1 < len(toks) and _is_word_num(toks[i + 1])):
            if t != "and":
                run.append(t)
            continue
        _flush(run, out)
        run = []
        if t in ORDINALS:
            out.add(str(ORDINALS[t]))
    _flush(run, out)
    return out


def same(a, b) -> bool:
    ca, cb = canon(a), canon(b)
    return ca is not None and ca == cb


def strip_numbers(text: str) -> str:
    """The words of a text without its numbers (and the symbols that belonged to them): words-only."""
    s = re.sub(r"[$£€]?\s?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d*\.\d+|\d+)\s?(?:%|[xXkKmMbB]\b|\+)?", " ", str(text or ""))
    return re.sub(r"\s{2,}", " ", s).strip(" ,.:;|-")
