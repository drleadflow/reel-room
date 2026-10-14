"""rrkit: Reel Room's shared motion component kit (13 pieces every style can drop in).

    import sys; sys.path.insert(0, "<SK>/templates/kit"); import rrkit
    k = rrkit.Kit(brand, words)                      # brand.json dict, words.json rows (cut seconds)
    p = k.typer(text="order a full metabolic panel", at="@get", type_until="@panel^", send="@that",
                done="Panel ordered", done_at="@everything", until=18.4)
    html = rrkit.mount(cx_or_tl, p)                  # split Ctx or stylekit TL: tweens + SFX go in, html comes back

Every piece is plain HTML + CSS + one call into the kit runtime (window.RRK, kit_*.js), built on the Motion v2 tokens
(RRM.EASE / RRM.q from engine/motion/motion.js; the runtime carries the same table as a fallback when motion is off).
Pieces are seek-safe and deterministic: hidden states are set once at build, every event is quantised onto its frame,
entrances are fromTo(immediateRender:false), per-frame values (counters, wipes) are one tl.set per frame, no randomness
outside a seeded generator. Colours and fonts come only from brand.json. Times are word-anchored:
  number          seconds after the kit's base (split beat start; 0 for full-frame styles = cut seconds)
  "@word"         start of the first matching word, searched IN ORDER from the piece's previous anchor
  "@word:2"       second match;  "@word+0.2" / "@word-0.1" offset;  "@word^" the word's END
Visual anchors land a named lead before the word (visual 0.04 s, stamp 0.03, type 0.05).
Each piece emits SFX events {t, kind, sound, what, level}; level "light" events are the default set (sparse, the hero
moments), "full" adds the small ones (typing ticks, rows). mount() forwards the chosen level to the host's mixer.

Components (id: plain-language name; method):
  typer            "type it like a prompt"          Kit.typer
  checklist-tick   "tick them off"                   Kit.checklist
  progress-bar     "fill the bar"                    Kit.progress
  odometer         "count it up"                     Kit.odometer
  label-pill       "pop a label" / "strike it out"   Kit.pill
  receipt          "print the receipt"               Kit.receipt
  comment-cta      "comment for the DM"              Kit.comment_dm
  stepper          "show the steps"                  Kit.stepper
  annotation-arrow "draw an arrow at it"             Kit.annotate
  phone-frame      "shrink me into a phone"          Kit.phone
  before-after     "wipe before to after"            Kit.before_after
  spotlight        "spotlight it"                    Kit.spotlight
  head-bubble      "put my head in a bubble"         Kit.head_bubble
Docs: references/kit.md.

Parts of the typer and comment-cta pieces are adapted from reel-kit (fx/prompt-bar, fx/comment-cta),
Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md at the repository root).
"""
import os
import sys

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rrkit_base import (Kit, Piece, DEFAULT_BRAND, SAFE, SOUND_OF, STYLEKIT_SOUND, HERE, JS_FILES, CSS_FILE,  # noqa: F401
                        box, esc, fr, mix, place, q, rgba, sfx)

# ---------------------------------------------------------------------------------------------- runtime + mounting
def runtime_js():
    return "\n".join(open(os.path.join(HERE, f)).read() for f in JS_FILES)


def runtime_css():
    return open(os.path.join(HERE, CSS_FILE)).read()


def page_tags():
    """The kit runtime + stylesheet, once per page (mount() adds them to the first piece automatically)."""
    return f"<style data-rrk>\n{runtime_css()}\n</style>\n<script data-rrk>\n{runtime_js()}\n</script>\n"


def mount(host, piece, sfx_level="light", gain_db=0.0):
    """Hand a piece to a host composition and return its html (prefixed with the kit runtime the first time).
    host: split Ctx (tweens -> cx.tw, sounds -> cx.event), stylekit TL (tl.raw, tl.cue), or a dict
    {"js": [], "events": []} for hand-built pages."""
    first = not getattr(host, "_rrk_loaded", False) if not isinstance(host, dict) else not host.get("_rrk_loaded")
    if isinstance(host, dict):
        host.setdefault("js", []).extend(piece.js)
        host.setdefault("events", []).extend(piece.events(sfx_level))
        host["_rrk_loaded"] = True
    elif hasattr(host, "tw") and hasattr(host, "event"):          # split Ctx
        host.tw.extend(piece.js)
        for e in piece.events(sfx_level):
            host.event(e["t"], e["kind"] if e["kind"] != "type" else "tick", f"{piece.comp}: {e['what']}")
        host._rrk_loaded = True
    elif hasattr(host, "js") and hasattr(host, "cue"):            # stylekit TL
        host.js.extend(piece.js)
        for e in piece.events(sfx_level):
            name = STYLEKIT_SOUND.get(e["kind"])
            if name:
                host.cue(e["t"], name, gain_db)
        host._rrk_loaded = True
    else:
        raise TypeError("rrkit.mount: host must be a split Ctx, a stylekit TL or a dict")
    return (page_tags() if first else "") + piece.html


def mixer_events(pieces, level="light"):
    """Events for engine/motion/mixer.build_bus(events, ...) when a page mixes its own sound."""
    out = []
    for p in pieces:
        for e in p.events(level):
            out.append({"t": e["t"], "kind": e["kind"] if e["kind"] != "type" else "tick", "what": f"{p.comp}: {e['what']}"})
    return sorted(out, key=lambda e: e["t"])


# ---------------------------------------------------------------------------------------------- registry
from comps_ui import UI  # noqa: E402
from comps_fx import FX  # noqa: E402
from comps_pip import PIP  # noqa: E402

for _name, _fn in {**UI, **FX, **PIP}.items():
    setattr(Kit, _name, _fn)

COMPONENTS = {
    "typer": {"method": "typer", "say": ["type it like a prompt", "show me typing it", "prompt bar"],
              "what": "a pill opens into a prompt bar, types your words letter by letter, sends, and shows the result"},
    "checklist-tick": {"method": "checklist", "say": ["tick them off", "checklist", "check them as I say them"],
                       "what": "a card lists the items and ticks each one on its word"},
    "progress-bar": {"method": "progress", "say": ["fill the bar", "progress bar", "show how far along"],
                     "what": "a bar fills in steps on your words with a rolling percentage"},
    "odometer": {"method": "odometer", "say": ["count it up", "roll the number", "odometer"],
                 "what": "a big number rolls up like a mechanical counter and locks on the word"},
    "label-pill": {"method": "pill", "say": ["pop a label", "strike it out", "cross it off and drop it"],
                   "what": "a label pill pops in with a burst; it can get struck through and tumble away"},
    "receipt": {"method": "receipt", "say": ["print the receipt", "price stack", "add it up"],
                "what": "a receipt prints line by line on your words, totals up and gets stamped"},
    "comment-cta": {"method": "comment_dm", "say": ["comment for the DM", "comment the keyword", "show the DM"],
                    "what": "an Instagram comment types your keyword, then the DM with the link lands"},
    "stepper": {"method": "stepper", "say": ["show the steps", "step tracker", "part 1 of 4"],
                "what": "a step tracker lists the parts and lights up the one you are on"},
    "annotation-arrow": {"method": "annotate", "say": ["draw an arrow at it", "circle it", "underline it"],
                         "what": "a hand-drawn arrow, circle or underline draws on with a handwritten label"},
    "phone-frame": {"method": "phone", "say": ["shrink me into a phone", "put me on a phone screen"],
                    "what": "the video shrinks into a phone frame (and can grow back out)"},
    "before-after": {"method": "before_after", "say": ["wipe before to after", "before and after", "slider"],
                     "what": "a tilted divider wipes the before look into the after"},
    "spotlight": {"method": "spotlight", "say": ["spotlight it", "dim everything else", "focus on this"],
                  "what": "the frame dims except one region, which can move to the next thing"},
    "head-bubble": {"method": "head_bubble", "say": ["put my head in a bubble", "picture in picture me",
                                                     "shrink me into a corner"],
                    "what": "you shrink into a circle in a top corner while a full-screen graphic plays, then grow back"},
}


def build(kit, comp, **args):
    """Planner entry: build a component by id with JSON args, e.g. build(k, 'typer', text=..., at='@cut')."""
    if comp not in COMPONENTS:
        raise KeyError(f"unknown kit component '{comp}'; known: {', '.join(COMPONENTS)}")
    return getattr(kit, COMPONENTS[comp]["method"])(**args)


from comps_chart import register as _register_chart  # noqa: E402  evidence-chart (comps_chart.py)
_register_chart(Kit, COMPONENTS)

import heroes as _heroes  # noqa: E402  the hero library (heroes_*.py): typed, parameterised hero moments
_heroes.register(Kit, COMPONENTS)
HEROES = _heroes.catalog()

import beats_editorial as _beats  # noqa: E402  editorial-style everyday beats (ed-*), never in the hero catalogue
_beats.register(Kit, COMPONENTS)
