"""feed.py: the top-slot feeder (split engine, used by the kallaway preset in presets.py).

plan(...) chops every free stretch of a split segment into pictures of about `every` seconds (boundaries snapped to
word starts) and fills them from the project's B-roll:
  assets/broll/broll.json  {"items": [{"src": "assets/broll/a.mp4", "word": "blood", "seg": "n1a", "media_start": 0.4,
                            "arrow": {"at": "@insulin", "to": [700, 520], "from": [260, 780], "label": "this one"}}]}
                            (items with "word" are pinned to the picture where that word is spoken; the rest go in order)
  or every image/video file in assets/broll/, sorted by name.
When the B-roll runs out the feed falls back to kit cards (the window's key word on a brand card), so the top slot
never sits still. Inserts: feed_item (clip / still / screen with a slow push or drift, hard cut in), feed_card.
"""
import json
import os
import re

from ctx import esc, snap
import inserts_media as media

MEDIA_EXT = (".mp4", ".mov", ".webm", ".m4v", ".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
FEED_INSERTS = ("feed_item", "feed_card")
STOP = set("a an the and or but so to of in on at for with is are was were be it its this that you your i me my we "
           "our they he she do does did not if then as by from up out about into just can will would could should have "
           "has had there here what which who how when where why i'm i've you're it's that's get got also".split())
TONES = ("paper", "ink", "accent")


def _norm(t):
    return re.sub(r"[^\w']+", "", str(t).lower())


def sources(project, rel_dir="assets/broll"):
    """-> list of B-roll dicts {"src", ...} from broll.json, else the sorted media files of the folder."""
    d = os.path.join(project, rel_dir)
    js = os.path.join(d, "broll.json")
    if os.path.exists(js):
        try:
            with open(js) as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit(f"feed: cannot read {js}: {e}")
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        out = []
        for it in items:
            it = {"src": it} if isinstance(it, str) else dict(it)
            if not it.get("src"):
                raise SystemExit(f"feed: broll.json item without src: {it}")
            out.append(it)
        return out
    if not os.path.isdir(d):
        return []
    return [{"src": f"{rel_dir}/{n}"} for n in sorted(os.listdir(d)) if n.lower().endswith(MEDIA_EXT)]


def chop(t0, t1, words, every=1.0, lo=0.8, hi=1.4):
    """Boundaries of the pictures in [t0, t1]: about `every` s each, snapped to a word start within 0.25 s."""
    span = t1 - t0
    n = max(1, round(span / every))
    if span / n > hi:
        n += 1
    while n > 1 and span / n < lo:
        n -= 1
    starts = [w["start"] for w in words if t0 + 0.4 < w["start"] < t1 - 0.4]
    cuts = [t0]
    for i in range(1, n):
        ideal = t0 + span * i / n
        near = [s for s in starts if abs(s - ideal) <= 0.25 and s - 0.03 - cuts[-1] >= lo and t1 - s + 0.03 >= lo * (n - i)]
        fallback = min(max(ideal, cuts[-1] + lo), t1 - lo * (n - i))     # never leaves a piece under lo
        cuts.append(round(min(near, key=lambda s: abs(s - ideal)) - 0.03, 3) if near else round(fallback, 3))
    return list(zip(cuts, cuts[1:] + [t1]))


def keyword(words, t0, t1):
    """The window's key word for a fallback card: the longest content word spoken in it (or just before)."""
    inside = [w for w in words if t0 - 0.05 <= w["start"] < t1]
    cand = [w for w in inside if _norm(w["text"]) not in STOP and len(_norm(w["text"])) > 2] or inside
    if not cand:
        prev = [w for w in words if w["start"] < t0]
        cand = prev[-1:] or words[:1]
    best = max(cand, key=lambda w: (len(_norm(w["text"])), -w["start"]))
    return re.sub(r"[^\w'%$.-]+", "", best["text"]).strip(".").upper()


def _pinned_slot(it, slots, words, seg_times):
    lo, hi = seg_times.get(it.get("seg"), (0.0, 1e9))
    w = next((w for w in words if lo - 0.05 <= w["start"] < hi and _norm(w["text"]) == _norm(it["word"])), None)
    if w is None:
        return None
    return next((i for i, (a, b) in enumerate(slots) if a - 0.05 <= w["start"] < b), None)


def plan(ranges, words, srcs, seg_times, cfg):
    """ranges: [(t0, t1)] free top-slot stretches -> project beats (feed_item / feed_card), plus a report."""
    slots = []
    fr = lambda t: round(t * 30) / 30   # noqa: E731  pictures start ON a frame, kept exact (a 4-decimal round can
    #                                       land a video's data-start just after its frame, one frame late)
    for a, b in ranges:
        if b - a >= 0.5:
            slots += [(fr(x), fr(y)) for x, y in chop(a, b, words, cfg.get("every", 1.0), cfg.get("min", 0.8), cfg.get("max", 1.4))]
    pick = [None] * len(slots)
    rest = []
    for it in srcs:
        i = _pinned_slot(it, slots, words, seg_times) if it.get("word") else None
        if i is not None and pick[i] is None:
            pick[i] = it
        else:
            rest.append(it)
    for i in range(len(slots)):
        if pick[i] is None and rest:
            pick[i] = rest.pop(0)
    beats, n_card = [], 0
    for i, ((a, b), it) in enumerate(zip(slots, pick)):
        args = {"i": i, "swish": i % max(1, int(cfg.get("swish_every", 2))) == 0, "push": cfg.get("push", 0.06),
                "drift": cfg.get("drift", 26)}
        if it is None:
            args.update(word=keyword(words, a, b), tone=TONES[n_card % len(TONES)])
            n_card += 1
            beats.append({"at": a, "until": b, "layout": "split", "insert": "feed_card", "args": args})
        else:
            args.update({k: v for k, v in it.items() if k not in ("word", "seg")})
            beats.append({"at": a, "until": b, "layout": "split", "insert": "feed_item", "args": args})
    lens = [round(b - a, 3) for a, b in slots]
    return beats, {"pictures": len(slots), "broll": len(slots) - n_card, "cards": n_card, "unused_broll": len(rest),
                   "intervals": lens, "mean": round(sum(lens) / len(lens), 3) if lens else None}


def _motion(cx, sel, beat, a):
    """Slow push (even pictures) or a lateral drift (odd pictures) across the picture's whole life."""
    t0, dur = beat["t0"], max(0.1, beat["t1"] - beat["t0"])
    push, drift = float(a.get("push", 0.06)), float(a.get("drift", 26))
    if a.get("i", 0) % 2 == 0:
        frm, to = {"scale": 1.0}, {"scale": 1.0 + push}
    else:
        sgn = 1 if (a.get("i", 0) // 2) % 2 == 0 else -1
        frm, to = {"scale": 1.0 + push, "x": -sgn * drift}, {"scale": 1.0 + push, "x": sgn * drift}
    to.update(duration=round(dur, 3), ease="none")
    cx.tw.append(f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(to)},{snap(t0)});")


def _cut_in(cx, beat, a, what):
    cx.event(beat["t0"], "flip" if a.get("swish") else "cut", what)


def feed_item(cx, beat, a):
    """One B-roll picture filling the top slot (1080 x 960): a clip, a still or a screen recording."""
    src = a["src"]
    fid = cx.uid("fd")
    is_vid = src.lower().endswith(VIDEO_EXT)
    if is_vid:
        inner = media._video(cx, beat, src, 0, 0, 1080, 960, a.get("media_start", 0.0), a.get("autocrop", False))
    elif a.get("kind") == "screen":     # a screenshot in a window frame on the brand ground (arrows land on it)
        cx.check_asset(src)
        iw, ih = cx.img_size(src)
        h = round(960 * ih / iw)
        inner = (f'<div class="fd-ground"></div><div class="fd-scr" style="height:{h + 58}px"><div class="fd-bar"><i></i><i></i><i></i></div>'
                 f'<div class="fd-shot" style="height:{h}px;background-image:url(\'{esc(src)}\')" {cx.box("image", beat["t0"], beat["t1"])}></div></div>')
    else:
        cx.check_asset(src)
        inner = (f'<div class="fd-img" style="background-image:url(\'{esc(src)}\');background-position:{a.get("pos", "50% 50%")}" '
                 f'{cx.box("image", beat["t0"], beat["t1"])}></div>')
    _motion(cx, f"#{fid}", beat, a)
    _cut_in(cx, beat, a, f"feed {os.path.basename(src)}")
    arrow = _arrow(cx, beat, a.get("arrow")) if a.get("arrow") else ""
    return f'<div class="fd" id="{fid}">{inner}</div>{arrow}'


def _arrow(cx, beat, spec):
    """An annotation arrow (kit) that lands on the spoken noun over a screen."""
    import kitbridge
    k = kitbridge.kit(cx, beat)
    p = k.annotate(tuple(spec["to"]), kind=spec.get("kind", "arrow"), at=spec.get("at", 0.2), label=spec.get("label"),
                   frm=tuple(spec["from"]) if spec.get("from") else None, until=spec.get("until"),
                   color=spec.get("color", "accent"), size=spec.get("size", 64), seed=spec.get("seed", 7))
    return kitbridge.mount(cx, p)


def feed_card(cx, beat, a):
    """Fallback picture: the window's key word on a kit-style brand card (tone cycles paper / ink / accent)."""
    cid = cx.uid("fc")
    word = esc(a.get("word") or "")
    t0, t1 = beat["t0"], beat["t1"]
    cx.enter(beat, f"#{cid} .fc-w", t0, {"y": 34, "scale": 1.06, "filter": "blur(5px)"},   # readable on the cut frame
             {"y": 0, "scale": 1, "filter": "blur(0px)"}, dur=0.3, ease="expo.out")
    cx.enter(beat, f"#{cid} .fc-rule", t0 + 0.12, {"scaleX": 0}, {"scaleX": 1}, dur=0.32, ease="expo.out")
    _motion(cx, f"#{cid} .fc-bg", beat, a)
    _cut_in(cx, beat, a, f"feed card {a.get('word')}")
    return (f'<div class="fc fc-{a.get("tone", "paper")}" id="{cid}" {cx.box("card", t0, t1)}><div class="fc-bg"></div>'
            f'<div class="fc-in"><div class="fc-mask"><div class="fc-w" data-fit="900,70" {cx.box("text", t0, t1, True)}>{word}</div></div>'
            f'<div class="fc-rule"></div></div></div>')


def css(brand):
    c, f = brand["colors"], brand["fonts"]
    return f"""
.fd{{position:absolute;left:0;top:0;width:1080px;height:960px;transform-origin:540px 560px}}
.fd-img{{position:absolute;inset:0;background-size:cover;background-repeat:no-repeat}}
.fd-ground{{position:absolute;inset:-40px;background:{c['bg']}}}
.fd-scr{{position:absolute;left:60px;top:250px;width:960px;border-radius:28px;overflow:hidden;background:#fff;
  box-shadow:0 34px 64px rgba(20,10,12,.22),0 10px 22px rgba(20,10,12,.12)}}
.fd-bar{{height:58px;display:flex;align-items:center;gap:10px;padding:0 22px;background:{c['bg']};border-bottom:1.5px solid rgba(20,10,12,.08)}}
.fd-bar i{{width:14px;height:14px;border-radius:7px;background:rgba(20,10,12,.18)}}
.fd-shot{{width:100%;background-size:100% 100%;background-repeat:no-repeat}}
.fc{{position:absolute;left:0;top:0;width:1080px;height:960px;overflow:hidden}}
.fc-bg{{position:absolute;inset:-40px;transform-origin:540px 560px;
  background-image:radial-gradient(circle,currentColor 2px,transparent 2.6px);background-size:46px 46px}}
.fc-paper{{background:{c['bg']};color:rgba(0,0,0,.07)}}.fc-ink{{background:{c['ink']};color:rgba(255,255,255,.06)}}
.fc-accent{{background:{c['accent']};color:rgba(255,255,255,.08)}}
.fc-in{{position:absolute;left:0;right:0;top:300px;height:420px;display:flex;flex-direction:column;align-items:center;justify-content:center}}
.fc-mask{{overflow:hidden;padding:0 20px 8px}}
.fc-w{{font:900 150px/1.02 '{f['display']}',sans-serif;letter-spacing:-.045em;white-space:nowrap}}
.fc-paper .fc-w{{color:{c['ink']}}}.fc-ink .fc-w{{color:{c['bg']}}}.fc-accent .fc-w{{color:{c['bg']}}}
.fc-rule{{width:180px;height:10px;border-radius:5px;margin-top:26px;transform-origin:0 50%;background:{c['accent']}}}
.fc-accent .fc-rule,.fc-ink .fc-rule{{background:{c.get('highlight', c['bg'])}}}
"""


INSERTS = {"feed_item": feed_item, "feed_card": feed_card}
