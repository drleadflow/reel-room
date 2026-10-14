"""Split-engine inserts the plan compiler writes (loaded by templates/split/compose.py, `load_plan_inserts`).

  {"insert": "kit", "args": {"comp": "<rrkit component id>", ...kit args}}   any rrkit piece inside a split beat
  {"insert": "word_card", "args": {"text": "...", "at": "@word", "hero": false}}   one big verbatim phrase on a card
  {"insert": "hero", "args": {"comp": "<hero id>", ...contract}}   a library hero (templates/kit/heroes_*.py)
  {"insert": "ground", "args": {"tone": "dark"}}   the colour-set ground under a split-panel kit piece
  {"insert": "beat", "args": {"comp": "ed-headline", ...}}   an everyday editorial beat (templates/kit/beats_editorial.py)

Both follow the split insert contract fn(cx, beat, args) -> html: times are seconds after the beat start or
'@word' anchors inside the beat, colours and fonts come from brand.json, every readable box carries data-box tags so
compose measures it for QA. This file is loaded by path (no sys.path entry), so it imports nothing from engine/.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(os.path.dirname(HERE))
KIT_DIR = os.path.join(SK, "templates", "kit")
SPLIT_DIR = os.path.join(SK, "templates", "split")
for _p in (KIT_DIR, SPLIT_DIR):
    if _p not in sys.path:
        sys.path.append(_p)

import inspect  # noqa: E402

import rrkit  # noqa: E402
from ctx import esc, snap  # noqa: E402
from heroes_base import GROUND_CSS, HEROES, Stage, ensure_fonts, set_vars  # noqa: E402

PRIVATE = ("comp", "_alone", "_area", "_layout")
WORD_W = 960            # card width: the hero graphic of its beat (qa hero_scale wants >= 60 % of 1080)
WORD_MAX_PX = {False: 150, True: 190}
TEXT_LEAD = 0.3        # seconds after the card lands that its words are readable
WORD_CSS = """
.wc-card{position:absolute;left:60px;width:960px;border-radius:44px;background:var(--wc-paper);
  box-shadow:0 34px 64px rgba(0,0,0,.16),0 10px 22px rgba(0,0,0,.10);display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:46px 54px;box-sizing:border-box}
.wc-card.hero{background:var(--wc-acc)}
.wc-t{font-family:var(--wc-fd);font-weight:900;line-height:1.04;letter-spacing:-.01em;word-spacing:.1em;color:var(--wc-acc);
  text-align:center;white-space:nowrap}
.wc-card.hero .wc-t{color:var(--wc-on)}
.wc-bar{position:absolute;left:54px;right:54px;bottom:26px;height:9px;border-radius:6px;background:var(--wc-hl);transform-origin:0 50%}
"""


def _kit_args(a):
    return {k: v for k, v in a.items() if k not in PRIVATE}


def kit(cx, beat, a):
    """Mount one rrkit piece in this beat. Plain-number times are seconds after the beat start (Kit.for_split)."""
    comp = a.get("comp")
    if comp not in rrkit.COMPONENTS:
        raise SystemExit(f"kit insert in beat {beat['id']}: unknown component {comp!r}; known: {sorted(rrkit.COMPONENTS)}")
    k = rrkit.Kit.for_split(cx, beat)
    args = _kit_args(a)
    if beat["layout"] != "split" and comp not in ("phone-frame", "before-after", "spotlight", "annotation-arrow"):
        args.setdefault("y", a.get("_area", (250, 0))[0] + 30)
    piece = rrkit.build(k, comp, **args)
    return rrkit.mount(cx, piece, sfx_level=a.get("sfx", "light"))


def _vars(cx):
    c, f = cx.brand["colors"], cx.brand["fonts"]
    paper = rrkit.mix(c["bg"], "#ffffff", 0.35)
    return (f"--wc-paper:{paper};--wc-acc:{c['accent']};--wc-hl:{c.get('highlight', c['accent'])};"
            f"--wc-on:{rrkit.mix(c['bg'], '#ffffff', 0.5)};--wc-fd:'{f['display']}',system-ui,sans-serif")


def _size(lines, hero):
    """Font size that fits the longest line on one line (data-fit shrinks it further after the fonts load)."""
    longest = max((len(x) for x in lines), default=1)
    return int(min(WORD_MAX_PX[hero], max(56, 852 / (0.6 * max(3, longest)))))


def word_card(cx, beat, a):
    """One big phrase, verbatim, on a brand card: the card lands on the beat start, the words push up through a mask
    right after (never an empty card), take a small stamp on their spoken word and an underline draws there.
    hero=True: accent card, bigger type."""
    text, hero = str(a["text"]), bool(a.get("hero"))
    lines = [x.strip() for x in text.split("\n") if x.strip()] or [text]
    wid, t0, t1 = cx.uid("wc"), beat["t0"], beat["t1"]
    a0 = beat.get("anchor_t0", t0)
    t_word = max(t0, cx.when(a.get("at"), beat, 0.15) - 0.04)
    t_text = min(t_word, a0 + TEXT_LEAD)     # never an empty card: the words are in by TEXT_LEAD after the cut
    px = _size(lines, hero)
    h = int(92 + len(lines) * px * 1.06)
    y0, y1 = a.get("_area", (220, 940))
    top = a.get("y", round(y0 + (y1 - y0 - h) / 2))
    cx.enter(beat, f"#{wid}", a0, {"opacity": 0, "y": 50, "scale": 0.94, "filter": "blur(12px)"},
             {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, dur=0.42, ease="expo.out")
    sel = [f"#{wid}t{i}" for i in range(len(lines))]
    cx.init.append(f"gsap.set({json.dumps(sel)},{{autoAlpha:0}});gsap.set({json.dumps('#' + wid + 'u')},{{scaleX:0}});")
    for i, s in enumerate(sel):
        cx.tw.append(f"RRM.enter('maskPush',tl,{json.dumps(s)},{snap(t_text + 0.08 * i)},{{dur:0.34}});")
    if t_word > t_text + 0.3:                 # the spoken word lands later: the type takes a small stamp on it
        cx.tw.append(f"tl.fromTo({json.dumps(sel)},{{scale:1.07}},{{scale:1,duration:0.4,"
                     f"ease:'elastic.out(1,0.45)',immediateRender:false}},{snap(t_word)});")
    cx.tw.append(f"tl.fromTo({json.dumps('#' + wid + 'u')},{{scaleX:0}},{{scaleX:1,duration:0.5,ease:'expo.inOut',"
                 f"immediateRender:false}},{snap(t_word + 0.05)});")
    cx.event(a0, "whoosh", f"word card {text[:16]}")
    style = "" if getattr(cx, "_wc_css", False) else f"<style>{WORD_CSS}</style>"
    cx._wc_css = True
    rows = "".join(f'<div class="wc-t" id="{wid}t{i}" data-fit="852,40" style="font-size:{px}px" '
                   f'{cx.box("text", t_text, t1, True)}>{esc(x)}</div>' for i, x in enumerate(lines))
    return (f'{style}<div class="wc-card{" hero" if hero else ""}" id="{wid}" style="top:{top}px;{_vars(cx)}" '
            f'{cx.box("card", t0, t1)}{" data-hero" if hero else ""}>{rows}<span class="wc-bar" id="{wid}u"></span></div>')


def _face(cx, beat):
    """(cx, cy, h) of the speaker's face on screen over the beat (median of the tracked skin boxes)."""
    rows = cx._rows(beat["t0"], beat["t1"]) if hasattr(cx, "_rows") else []
    skins = sorted((r[3]["x"] + r[3]["w"] / 2, r[3]["y"] + r[3]["h"] / 2, r[3]["h"]) for r in rows if r[3])
    if not skins:
        return (540, 900, 200)
    mid = skins[len(skins) // 2]
    return tuple(round(v) for v in mid)


def hero(cx, beat, a):
    """Mount one library hero. split -> the top slot (colour-set ground); card / stage -> the paper stage (cream set);
    full -> over the full-frame speaker (face from the track)."""
    comp = a.get("comp")
    c = HEROES.get(comp)
    if not c:
        raise SystemExit(f"hero insert in beat {beat['id']}: unknown hero {comp!r}; known: {sorted(HEROES)}")
    layout = a.get("_layout", "split")
    layout = {"overlay": "full", "media": "stage"}.get(layout, layout)
    args = _kit_args(a)
    params = inspect.signature(c["fn"]).parameters
    args.setdefault("layout", layout)
    if layout != "split":
        args.setdefault("area", list(a.get("_area", (240, 900))))
    if layout in ("card", "stage"):
        args["tone"] = "cream"
    if "face" in params and layout == "full":
        args.setdefault("face", _face(cx, beat))
    args = {k: v for k, v in args.items() if k in params}
    ensure_fonts(cx.dir)
    piece = rrkit.build(rrkit.Kit.for_split(cx, beat), comp, **args)
    return rrkit.mount(cx, piece, sfx_level=a.get("sfx", "light"))


def ground(cx, beat, a):
    """A colour-set ground over the whole split panel (on from the beat's first frame, settling from a slight push): no
    empty cream panel
    under a kit piece. Nothing readable, no data-box."""
    kit = rrkit.Kit(cx.brand)
    tone = a.get("tone", "cream")
    gid = cx.uid("gnd")
    a0 = beat.get("anchor_t0", beat["t0"])
    cx.tw.append(f"tl.fromTo({json.dumps('#' + gid + 'gr')},{{scale:1.06}},{{scale:1,duration:0.7,ease:'power2.out',"
                 f"immediateRender:false}},{snap(max(beat['t0'], a0))});")
    return (f"<style>{GROUND_CSS}</style><div class=\"rrh\" style=\"{set_vars(kit, tone)}\">"
            f"{Stage('split').ground(gid, tone, kit)}</div>")


def beat(cx, beat_, a):
    """Mount one everyday editorial beat (templates/kit/beats_editorial.py): split -> the top slot on its colour-set
    ground; full / overlay -> a compact card in the band above the head."""
    import beats_editorial
    comp = a.get("comp")
    c = beats_editorial.BEATS.get(comp)
    if not c:
        raise SystemExit(f"beat insert in beat {beat_['id']}: unknown beat {comp!r}; known: {sorted(beats_editorial.BEATS)}")
    layout = {"card": "full", "stage": "full", "media": "full"}.get(beat_["layout"], beat_["layout"])
    params = inspect.signature(c["fn"]).parameters
    args = {k: v for k, v in _kit_args(a).items() if k in params}
    args["layout"] = "split" if layout == "split" else "full"
    if layout != "split":
        args.setdefault("area", list(a.get("_area", (250, 640))))
    ensure_fonts(cx.dir)
    piece = rrkit.build(rrkit.Kit.for_split(cx, beat_), comp, **args)
    return rrkit.mount(cx, piece, sfx_level=a.get("sfx", "light"))


INSERTS = {"kit": kit, "word_card": word_card, "hero": hero, "ground": ground, "beat": beat}
