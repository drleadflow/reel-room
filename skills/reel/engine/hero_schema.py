"""Typed contracts for the hero library (templates/kit/heroes_*.py): the catalogue text a model reads, and the
validator every filled hero passes before the compiler uses it. Pure functions (no model calls). Each validator
returns None when the args are usable, else one short error the model gets back on retry.

Rules (same as plan_schema.py): on-screen words and numbers come from the spoken line or its neighbours (invented()),
no em dashes, anchors are words of THIS line, colours are brand colour sets only, a citation must come from the
project's own sources. Fields of type media / data are filled by the compiler, never by the model.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import plan_schema as PS

KIT = Path(__file__).resolve().parent.parent / "templates" / "kit"
if str(KIT) not in sys.path:
    sys.path.append(str(KIT))
import heroes as _H  # noqa: E402

HEROES = _H.HEROES
SETS = ("cream", "dark", "tan", "accent")
COMPILER_FIELDS = ("media",)          # the compiler supplies these (thumbnails, clips), never the model
COMPILER_KEYS = ("until",)            # the compiler ends a hero with its beat; the model never sets these
TIMING = """Timing fields are '@word' anchors from THIS LINE:
  at = when the hero enters (leave it out to enter on the cut; for word-stamp it is the word that stamps);
  land / stamp / stamp_at / burn / pick_at / play_at / sticker_at / draw = the PAYOFF: the big moment lands on
  the line's key word (usually the planned anchor word);
  marks / lines_at / chapter_at / steps = one word per label or step, in spoken order;
  setup_at / ignite / fan_at / sub_at / label_at = an earlier or later supporting word."""
ANCHOR = re.compile(r"^@([^:^+\s]+?)(?::(\d+))?(\^)?([+-]\d*\.?\d+)?$")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def model_fields(hid: str) -> dict:
    return {k: v for k, v in HEROES[hid]["fields"].items() if v[0] not in COMPILER_FIELDS and k not in COMPILER_KEYS}


def required(hid: str) -> list:
    """Positional parameters of the hero method (no default) that the model must fill."""
    sig = inspect.signature(HEROES[hid]["fn"])
    return [p.name for p in list(sig.parameters.values())[1:] if p.default is inspect._empty
            and HEROES[hid]["fields"].get(p.name, ("",))[0] not in COMPILER_FIELDS]


def _desc(name, spec):
    t, o = spec
    if t == "text":
        return f"{name}: text<= {o[0]}{' (required)' if o[1] else ''}"
    if t == "texts":
        return f"{name}: [{o[0]}-{o[1]} texts <= {o[2]}]"
    if t == "anchors":
        return f"{name}: ['@word', ... up to {o[0]}]"
    if t == "enum":
        return f"{name}: one of {list(o[0])}"
    if t == "num":
        return f"{name}: number {o[0]}-{o[1]}"
    if t == "steps":
        return f"{name}: [[number, '@word'], ...] {o[0]}-{o[1]} steps"
    if t == "series":
        return f"{name}: [{{name, values:[numbers]}}] {o[0]}-{o[1]}"
    if t == "set":
        return f"{name}: colour set {list(SETS)}"
    return f"{name}: {t}"


def catalog_text(ids=None, compact=False) -> str:
    """One block per hero for a prompt: id, what it does, fields (model-filled only), min window, needs."""
    out = []
    for hid, c in HEROES.items():
        if ids is not None and hid not in ids:
            continue
        line = f"- {hid}: {c['what']}"
        if not compact:
            fields = "; ".join(_desc(k, v) for k, v in model_fields(hid).items())
            line += f"\n    fields: {fields}\n    needs >= {c['min_secs']:.1f} s" + \
                    (f"; needs {', '.join(c['needs'])}" if c["needs"] else "")
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- field checks
def _anchor_err(v, words) -> str | None:
    if v is None or isinstance(v, (int, float)):
        return None
    m = ANCHOR.match(str(v).strip())
    if not m:
        return f"anchor {v!r} must look like '@word'"
    w = m.group(1).lower().strip(".,!?;:'\"")
    if w not in words and not any(x.startswith(w) for x in words):
        return f"anchor {v!r}: '{w}' is not a word of THIS line"
    return None


def _text_err(v, limit, spoken, required_=False) -> str | None:
    if v is None or v == "":
        return "missing required text" if required_ else None
    if not isinstance(v, str):
        return f"{v!r} must be text"
    if len(v) > limit:
        return f"{v!r} is over {limit} chars"
    if PS.EM_DASH in v:
        return f"{v!r} has an em dash"
    if not re.search(r"[A-Za-z0-9]", v):        # a symbol: $, %, +, an arrow
        return None
    return PS.invented(v, spoken)


def _num_in(v, spoken):
    said = {x.replace(",", "") for x in _NUM.findall(spoken)}     # whole numbers ('0' is not in '100%')
    for n in _NUM.findall(str(v)):
        if n.replace(",", "") not in said:
            return f"number {n!r} was never said"
    return None


def _check_field(t, o, v, words, spoken, sources):
    if t == "text":
        return _text_err(v, o[0], spoken, o[1])
    if t == "texts":
        if not isinstance(v, list) or not o[0] <= len(v) <= o[1]:
            return f"needs a list of {o[0]}-{o[1]} texts"
        return next((e for e in (_text_err(x, o[2], spoken, True) for x in v) if e), None)
    if t == "anchor":
        return _anchor_err(v, words)
    if t == "anchors":
        if not isinstance(v, list) or len(v) > o[0]:
            return f"needs a list of up to {o[0]} anchors"
        return next((e for e in (_anchor_err(x, words) for x in v) if e), None)
    if t in ("num", "secs"):
        return None if isinstance(v, (int, float)) and o[0] <= v <= o[1] else f"needs a number {o[0]}-{o[1]}"
    if t == "bool":
        return None if isinstance(v, bool) else "needs true or false"
    if t == "enum":
        return None if v in o[0] else f"needs one of {list(o[0])}"
    if t == "set":
        return None if v in SETS else f"colour set must be one of {list(SETS)}"
    if t == "steps":
        if not isinstance(v, list) or not o[0] <= len(v) <= o[1] or any(not isinstance(s, (list, tuple)) or len(s) != 2 for s in v):
            return f"steps need {o[0]}-{o[1]} [number, '@word'] pairs"
        return next((e for e in ([_num_in(s[0], spoken) for s in v] + [_anchor_err(s[1], words) for s in v]) if e), None)
    if t == "series":
        return _series_err(v, o, spoken + " " + sources)
    if t == "source":
        if not sources.strip():
            return "no source in this project: a citation must come from the creator's own sources"
        return None if v and str(v).lower()[:24] in sources.lower() else f"citation {v!r} is not in the project's sources"
    if t == "pair":
        return None if v is None or (isinstance(v, list) and len(v) == 2) else "needs [group, series]"
    if t == "media":
        return None if isinstance(v, list) and o[0] <= len(v) <= o[1] else f"needs {o[0]}-{o[1]} media paths"
    return None


def _series_err(v, o, spoken):
    if not isinstance(v, list) or not o[0] <= len(v) <= o[1]:
        return f"series needs {o[0]}-{o[1]} entries"
    for s in v:
        if not isinstance(s, dict) or not isinstance(s.get("values"), list):
            return "each series needs {name, values}"
        e = next((x for x in (_num_in(n, spoken) for n in s["values"] if n not in (0, "0")) if x), None)
        if e:
            return e
    return None


def validate(hid: str, args: dict, line: str, context: str = "", sources: str = "") -> str | None:
    """None when `args` is a usable fill of hero `hid` for this line, else the first problem."""
    if hid not in HEROES:
        return f"unknown hero {hid!r}; use one of {sorted(HEROES)}"
    if not isinstance(args, dict):
        return "args must be an object"
    fields = model_fields(hid)
    extra = [k for k in args if k not in fields]
    if extra:
        return f"unknown field(s) {extra} for {hid}; allowed: {sorted(model_fields(hid))}"
    missing = [k for k in required(hid) if args.get(k) in (None, "", [])]
    if missing:
        return f"{hid} needs {missing}"
    words = PS.words_of(line)
    spoken = f"{line} {context}" + (f" {sources}" if "sources" in HEROES[hid]["needs"] else "")
    for k, v in args.items():
        t, o = fields[k]
        err = _check_field(t, o, v, words, spoken, sources)
        if err:
            return f"{k}: {err}"
    return None


def validator(hid_allowed: list, line: str, context: str = "", sources: str = ""):
    """llm_router.typed validator for {"hero": id | "none", "args": {...}}."""
    def check(d: dict) -> str | None:
        hid = d.get("hero")
        if hid == "none":
            return None
        if hid not in hid_allowed:
            return f"hero must be one of {hid_allowed} or 'none'"
        return validate(hid, d.get("args") or {}, line, context, sources)
    return check
