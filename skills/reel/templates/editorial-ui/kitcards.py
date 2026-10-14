"""Kit cards for editorial-ui (the plan compiler writes them; README "Cards"): rrkit pieces on the room footage.

  {"kind": "beat", "comp": "ed-headline" | "ed-number" | "ed-checklist" | "ed-contrast" | "ed-kicker", "args": {...}}
      an everyday editorial card (templates/kit/beats_editorial.py) in the band above the head, or under the chin
      when the head leaves no room above it
  {"kind": "kit", "comp": "<rrkit id>", "args": {...}}       any kit piece (comment-cta, ...) in the same band
  {"kind": "hero", "comp": "<hero id>", "args": {...}, "matte": true, "end_seg": "<seg id>"}
      a library hero over the footage, riding the camera with the speaker (<!--mvcam--> block). matte: the cut-out
      span (engine/cutout_cache.py) is laid over the hero so its type sits BEHIND the head (word-stamp,
      magazine-cover, reel-orbit). end_seg: the hero runs to the end of that later cut.
Times inside args: seconds after the card's cut, or '@word' anchors searched from that cut. Brand colours; fonts are
the editorial tokens (serif / ui / mono), so cards and headlines share one type system.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(SK, "templates", "kit"), os.path.join(SK, "engine")):
    if _p not in sys.path:
        sys.path.append(_p)

import inspect  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402

import rrkit  # noqa: E402
from heroes_base import HEROES, ensure_fonts  # noqa: E402

FPS = 30
KINDS = ("beat", "kit", "hero")
EXIT_S = 0.27                  # card exit tween (0.22 s) + a frame of margin before the cut
CAM_PAD = 40                   # px the motion camera's push can lift the face
HERO_Z = 5                     # heroes stack above the plate video inside the camera block (render layering)
TRACK0 = 60                    # data-track-index for hero matte videos (base 0, takeover webms below 60)
EST_H = {"ed-headline": 240, "ed-number": 220, "ed-checklist": 270, "ed-contrast": 240, "ed-kicker": 210,
         "comment-cta": 380}      # band card heights (beats_editorial BAND_K type sizes)


def _brand(pl, tok):
    b = dict(pl.proj.brand)
    b["fonts"] = {**b.get("fonts", {}), "serif": tok["serif"], "body": tok["ui"], "display": tok["serif"]}
    return b


def _kit(pl, s, c, tok):
    end = pl.seg(c["end_seg"]) if c.get("end_seg") else s
    k = rrkit.Kit(_brand(pl, tok), pl.proj.words_raw, base=s["t0"], end=end["t1"], prefix=f"e{c['id']}")
    # a card's or hero's exit (0.22 s) is done by the cut, so back-to-back pieces never overlap
    k.default_until = round(end["t1"] - EXIT_S, 4)
    return k


MIN_ABOVE = {"ed-headline": 100, "ed-kicker": 120, "ed-number": 115, "ed-contrast": 190}   # compact top-band card


SIDE_MIN_W, SIDE_PAD, EDGE = 300, 28, 40
COMPACT = {"ed-contrast": lambda a: {"text": a["right"], "at": a.get("land") or a.get("at"), "tone": a.get("tone")},
           "ed-kicker": lambda a: {"text": a["text"], "at": a.get("at"), "land": a.get("land"), "tone": a.get("tone")},
           "ed-number": lambda a: {"text": a["value"], "at": a.get("at"), "tone": a.get("tone")}}


def band(pl, s, comp, y, rows=0):
    """Upper third only (the showcase's layout discipline; never the torso). (area, above?) where area is [y0, y1] above the
    face (over the top of the head is fine, never the face), else [y0, y1, x, w] beside the head on its wider side,
    else None (the card is dropped: caption only)."""
    need = MIN_ABOVE.get(comp, 90 + 52 * rows if comp == "ed-checklist" else EST_H.get(comp, 300))
    face_h = s["chin"] - s["brow"]
    above = (y, int(s["brow"] - 0.18 * face_h - CAM_PAD))       # QA face pad + camera push
    if above[1] - above[0] >= need:
        return list(above), True
    left = int(s["head_x"][0]) - SIDE_PAD - EDGE
    right = 1080 - EDGE - 60 - int(s["head_x"][1]) - SIDE_PAD   # the right edge keeps the Reels UI column clear
    w = max(left, right)
    if w < SIDE_MIN_W:
        return None, False
    x = EDGE if left >= right else int(s["head_x"][1]) + SIDE_PAD
    return [y, int(s["chin"]), x, w], False


DATA_MIN_H = 200               # px: below this a data hero (counter, evidence chart) cannot be read


def above_band(pl, s, y=244):
    """[y0, y1] strictly above the face (QA face pad + camera push) for a data hero, else None."""
    face_h = s["chin"] - s["brow"]
    y1 = int(s["brow"] - 0.18 * face_h - CAM_PAD)
    return [y, y1] if y1 - y >= DATA_MIN_H else None


def _args(fn, args, extra):
    params = inspect.signature(fn).parameters
    return {k: v for k, v in {**args, **extra}.items() if k in params and v is not None}


def card(pl, s, c, y, tl, cues, tok):
    """(html, next y) for a "beat" / "kit" card in the cards layer."""
    ensure_fonts(pl.dir)
    comp = c["comp"]
    if comp not in rrkit.COMPONENTS:
        raise SystemExit(f"{c['kind']} card in {s['id']}: unknown kit piece {comp!r}")
    area, top = band(pl, s, comp, y, len((c.get("args") or {}).get("items") or []))
    if area is None and comp in COMPACT:                      # no room for the full card: its payoff as a headline
        c = {**c, "comp": "ed-headline", "args": COMPACT[comp](c.get("args") or {})}
        comp = "ed-headline"
        area, top = band(pl, s, comp, y)
    if area is None:
        pl.warn(f"{c['id']} {comp} in {s['id']}: no room above or beside the head, shown as caption only")
        return "", y
    k = _kit(pl, s, c, tok)
    fn = getattr(k, rrkit.COMPONENTS[comp]["method"])
    extra = {"layout": "full", "area": area} if c["kind"] == "beat" else {"y": area[0] + 6, "w": 900}
    piece = fn(**_args(fn, c.get("args", {}), extra))
    _events(tl, cues, piece, c, area)
    return rrkit.mount(tl, piece), (area[1] + 18 if top else y)


def add(body, pl, s, c, y, tl, tok):
    """compose.py hook: append a "beat" / "kit" card to the cards layer, return the next free y."""
    html, y = card(pl, s, c, y, tl, None, tok)
    body.append(html)
    return y


def _events(tl, cues, piece, c, area):
    """QA switch event: the card is substantially in two frames after its fly-in starts (it enters edge-on); the
    region is the card's always-covered core, so a compact card is not diluted by the band around it."""
    f0 = int(round(piece.t0 * FPS)) + 2          # the card flies in edge-on; it reads from its 3rd frame
    x, w = (area[2], min(area[3], 300)) if len(area) >= 4 else (390, 300)
    region = [x, area[0] + 10, w, min(100, area[1] - area[0] - 20)]
    tl.event(f0 / FPS, "enter", f"{c['id']} {c['comp']}", region=region, frame=f0)


def _face(pl, s):
    """(cx, cy, h) of the face in this cut, the heroes' convention (headpos.py facepos.json), else the track."""
    fp = pl.proj.p("work", "facepos.json")
    got = (json.load(open(fp)) if os.path.exists(fp) else {}).get(s["id"])
    if got:
        return round(got["cx"]), round(got["cy"]), round(got["h"])
    m = pl._seg_median(s)
    return tuple(round(v) for v in m) if m else (round(s["anchor"][0]), round(s["anchor"][1]), 220)


BEHIND = re.compile(r'class="(ws-w|mc-mh)" style="([^"]*?font-size:\s*\d+px[^"]*)" data-box="text"')


STACK = re.compile(r'class="ws-stack" style="top:(-?\d+)px;left:(-?\d+)px">(.*?)<div class="ws-w" style="font-size:(\d+)px"',
                   re.S)
SAFE_TOP, SAFE_SIDE, SETUP_H = 228, 62, 70     # side margin covers the 1.035 settle grow


def behind(html, face):
    """With a matte the word / masthead sits BEHIND the head: tag it "behind" (readable, safe-zone checked, but the
    head legitimately covers part of its foot, so the face-overlap check skips it), keep it inside the safe zone
    (narrower than the frame when the face is off centre, never above y 228)."""
    fit = max(400, 2 * min(face[0] - SAFE_SIDE, 1080 - SAFE_SIDE - face[0]))
    html = STACK.sub(_lower_stamp, html)
    return BEHIND.sub(lambda m: f'class="{m.group(1)}" style="{m.group(2)}" data-fit="{fit},90" data-box="behind"', html)


def _lower_stamp(m):
    """word-stamp: shrink the word until its stack starts at the safe top; the foot stays put (behind the head)."""
    top, left, setup, px = int(m.group(1)), m.group(2), m.group(3), int(m.group(4))
    up = SETUP_H if "ws-s" in setup else 0
    foot = top + px * 0.86 + up
    new_px = int(min(px, (foot - SAFE_TOP - up) / 0.86))
    new_top = round(foot - new_px * 0.86 - up)
    return (f'class="ws-stack" style="top:{new_top}px;left:{left}px">{setup}<div class="ws-w" '
            f'style="font-size:{new_px}px"')


def hero(pl, s, c, n, tl, cues, tok):
    """html for one library hero (goes into the camera block with the speaker)."""
    ensure_fonts(pl.dir)
    comp = c["comp"]
    if comp not in HEROES:
        raise SystemExit(f"hero card in {s['id']}: unknown hero {comp!r}")
    k = _kit(pl, s, c, tok)
    if c.get("data"):          # a data hero on its colour set: strictly the band above the head, never the face
        area = above_band(pl, s)
        if area is None:
            pl.warn(f"{c.get('id', '')} {comp} in {s['id']}: no room above the head, hero not drawn (compile checks "
                    "this with work/facepos.json; re-run compile_plan.py)")
            return ""
    else:
        area = (band(pl, s, "hero", 244)[0] or [244, 900])[:2]     # full-frame behind-the-head heroes
    extra = {"layout": "full", "face": _face(pl, s), "track": TRACK0 + 2 * n, "area": area, "z": HERO_Z}
    if c.get("matte"):
        import cutout_cache as CC
        end = pl.seg(c["end_seg"]) if c.get("end_seg") else s
        extra.update(CC.span_webm(pl.dir, s["f0"], min(pl.frames, end["f1"] + 8)))
    fn = HEROES[comp]["fn"]
    piece = fn(k, **_args(fn, c.get("args", {}), extra))
    html = rrkit.mount(tl, piece)
    return behind(html, extra["face"]) if c.get("matte") else html


def heroes_html(pl, tl, cues, tok):
    """Every hero card of the plan, in order (for the <!--mvcam--> block)."""
    out, n = [], 0
    for s in pl.segs:
        for c in [c for c in pl.cards if c["seg"] == s["id"] and c["kind"] == "hero"]:
            out.append(hero(pl, s, c, n, tl, cues, tok))
            n += 1
    return "".join(out)
