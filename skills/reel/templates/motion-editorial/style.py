"""MOTION EDITORIAL style: a paper-white motion-graphics stage on top, the speaker in a rounded card below, one-word
captions that swap between a bold sans and an italic serif accent. Graphics-only (`stage`) beats and full close-ups
(`full`) between. One hero graphic per beat, every element lands on its spoken word.

Loaded by templates/split/compose.py when project.json has "style": "motion-editorial". See README.md here.

Inserts (fn(cx, beat, args) -> html), all deterministic HTML/SVG + GSAP:
  kinetic     stacked words (sans / serif italic / mono), optional hand-drawn swoosh under one line
  numeral     giant serif numeral with a hand-drawn circle drawing around it + a mono label + a title
  cred_stack  numbered credential lines (01 / 02 / 03), each on its word
  lab_report  a paper lab report; rows land on words; optional zoom into one row + hand-drawn circle around it
  big_stat    mono label, a lead word, a giant number, a tag
  gauge       half-dial with a needle that swings on a word, end labels
  tiles       app-style icon tiles with soft shadows (icons: plate, dumbbell, drop, calendar, flask, heart)
  cal_flip    tear-off calendar page that flips to a second page on a word, with a circled mark
  media_stack full-frame B-roll plate for `media` beats: one clip, or top + bottom panels (hook.py)
  title_card  the hook title on a paper card that slams in on a hit (hook.py, use as a project overlay)
  cycle_chart a step-by-step drawn curve with brackets and numbered slots (chart.py)
"""
import json
import math
import os
import random
import sys

from ctx import esc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chart  # noqa: E402  (cycle_chart)
import hook  # noqa: E402   (media_stack, title_card)
import motionfx as fx  # noqa: E402  (motion v2 craft layer + stage rig)

DEFAULTS = {
    "fonts": {"serif": "Instrument Serif", "mono": "JetBrains Mono"},
    "italic_fonts": ["Instrument Serif"],
    "fonts_load": ['italic 400 120px "Instrument Serif"', '400 120px "Instrument Serif"', '500 30px "JetBrains Mono"',
                   '700 30px "JetBrains Mono"'],
    "card": {"top": 1040, "inset": 30, "radius": 72, "face_y": 1372, "scale": 1.0, "caption_band": 128},
    "stage_bottom": 1170,
    "captions": {"mode": "word", "strip_punct": True, "repeat_window": 3.6},
    "head_margin": 28,
}


# ----------------------------------------------------------------------------- helpers
def _top(a, h):
    if "y" in a:
        return a["y"]
    y0, y1 = a.get("_area", (220, 912))
    return round(y0 + (y1 - y0 - h) / 2)


def _scribble_path(cx_, cy_, rx, ry, seed=3, turns=1.12, tilt=-6):
    """Hand-drawn ellipse: a little more than one turn, wobbling radius, slightly tilted, open ends."""
    rnd = random.Random(seed)
    pts = []
    n = 64
    a0 = math.radians(rnd.uniform(200, 230))
    ph1, ph2 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
    tr = math.radians(tilt)
    for i in range(n + 1):
        u = i / n
        ang = a0 + u * turns * 2 * math.pi
        k = 1 + 0.035 * math.sin(3 * ang + ph1) + 0.02 * math.sin(5 * ang + ph2) + 0.05 * u
        x, y = rx * k * math.cos(ang), ry * k * math.sin(ang)
        pts.append((cx_ + x * math.cos(tr) - y * math.sin(tr), cy_ + x * math.sin(tr) + y * math.cos(tr)))
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1, 2):
        d += f" Q{pts[i][0]:.1f},{pts[i][1]:.1f} {pts[i + 1][0]:.1f},{pts[i + 1][1]:.1f}"
    return d


def _draw(cx, beat, sel, t, dur=0.5):
    return fx.draw(cx, beat, sel, t, dur)


def _land(cx, beat, sel, t, kind="rise", dur=None):
    """Graphic entrances (motionfx): rise = blur + scale + lift, pop = overshoot, slam = stamp + squash, slide = smear,
    cut = a fast blur settle with its beat, sheet = paper flies in tilted and lands, drop = falls, squashes, wobbles.
    Frame 1 of the reel stays static (it must read)."""
    return fx.land(cx, beat, sel, t, kind)


def _float(cx, beat, sel, t0, t1, amp=6):
    """Subtle idle float on a hero graphic (secondary motion while it holds; deterministic sine half-cycles)."""
    if not amp:
        return
    fx.bob(cx, beat, sel, t0 + 0.6, t1, amp=amp, period=2.4)


def _when(cx, beat, spec, d=0.0):
    return cx.when(spec, beat, d)


# ----------------------------------------------------------------------------- inserts
def _rule(cx, beat, uid, text, t, t1):
    """The magazine kicker rule around a mono label (hairlines draw out to the margins)."""
    return fx.kicker_rule(cx, beat, uid, t, t1, fx.label_w(text))


def kinetic(cx, beat, a):
    """lines: [{text, font: sans|serif|mono, size, color: ink|accent|gold|soft, at, enter: rise|pop|slam|slide|cut,
    mark: "@word" (a highlighter wipes in behind the line on that word)}]
    swoosh: {line: i, at}  (hand-drawn underline under that line)
    Lines rise letter by letter out of a mask (sans tight, serif with a lean), slam lines stamp in and squash,
    mono lines track in. Each line that lands on a word pulls the stage camera toward it."""
    kid, t0, t1 = cx.uid("kn"), beat["t0"], beat["t1"]
    lines = a["lines"]
    gap = a.get("gap", 6)
    hs = [int(l.get("size", 120) * (1.0 if l.get("font") != "mono" else 1.4)) for l in lines]
    h = sum(hs) + gap * (len(lines) - 1)
    top = _top(a, h)
    parts = []
    y = 0
    k_free = 0
    for i, l in enumerate(lines):
        lid = f"{kid}l{i}"
        if l.get("at") is None:
            t = _when(cx, beat, None, 0.14 * k_free)
            k_free += 1
        else:
            t = _when(cx, beat, l.get("at"), 0.0)
            fx.focus(cx, beat, t, top + y + hs[i] / 2)
        fnt = l.get("font", "sans")
        style = l.get("enter") if l.get("enter") in ("slam", "pop") else None
        fx.text_in(cx, beat, f"#{lid}t", t, fnt, style, len(l["text"]))
        if l.get("sfx"):
            cx.event(t, l["sfx"], f"kinetic {l['text']}")
        mark = ""
        if l.get("mark"):
            tm = _when(cx, beat, l["mark"], 0.6)
            fx.grow_x(cx, beat, f"#{lid}m", tm, 0.38)
            mark = f'<span class="mark" id="{lid}m"></span>'
        parts.append(f'<div class="kl {fnt} {l.get("color", "ink")}" id="{lid}" style="top:{y}px;height:{hs[i]}px;'
                     f'font-size:{l.get("size", 120)}px" data-fit="{a.get("max_w", 940)},40" {cx.box("text", max(t, t0), t1, True)}>'
                     f'<span class="klw">{mark}<span class="klt" id="{lid}t">{esc(l["text"])}</span></span></div>')
        y += hs[i] + gap
    sw = ""
    if a.get("swoosh"):
        s = a["swoosh"]
        li = s.get("line", len(lines) - 1)
        ly = sum(hs[:li + 1]) + gap * li - 6
        st = _when(cx, beat, s.get("at"), 0.3)
        _draw(cx, beat, f"#{kid}s path", st, 0.42)
        w = s.get("w", 560)
        d = f"M{540 - w / 2:.0f},{ly + 18} C{540 - w / 4:.0f},{ly - 4} {540 + w / 4:.0f},{ly + 26} {540 + w / 2:.0f},{ly + 4}"
        sw = (f'<svg class="sw" id="{kid}s" viewBox="0 0 1080 {h + 60}" style="top:0;height:{h + 60}px">'
              f'<path d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>')
    _float(cx, beat, f"#{kid}", beat.get("anchor_t0", t0), t1, a.get("float", 5))
    return f'<div class="kin" id="{kid}" style="top:{top}px;height:{h}px">{"".join(parts)}{sw}</div>'


def numeral(cx, beat, a):
    """n, label (mono kicker with a drawn rule), title (serif or sans, below, on its word), circle_at.
    The numeral stamps in from oversize and squashes; a giant outline echo of it slides in behind (depth) and drifts;
    the hand-drawn circle draws on its word; the title rises letter by letter."""
    nid, t0, t1 = cx.uid("nu"), beat["t0"], beat["t1"]
    size = a.get("size", 440)
    h = 60 + size * 0.86 + (150 if a.get("title") else 0)
    top = _top(a, h)
    tn = _when(cx, beat, a.get("at"), 0.0)
    _land(cx, beat, f"#{nid}n", tn, a.get("enter", "slam"))
    fx.focus(cx, beat, tn + 0.25, top + 60 + size * 0.43, 0.6)
    if a.get("at") is not None:
        cx.event(tn, a.get("sfx", "pop"), f"numeral {a['n']}")
    ghost = (f'<div class="nug" id="{nid}g" style="top:{60 + size * 0.43 - size * 0.8:.0f}px;font-size:{size * 1.9:.0f}px;'
             f'line-height:{size * 1.6:.0f}px;height:{size * 1.6:.0f}px">{esc(a["n"])}</div>')
    gt = fx.enter(cx, beat, f"#{nid}g", tn + 0.05, "blurIn", x=160, y=0, scale=1.15, blur=18, dur=0.7)
    if gt < t1 - 0.5:
        cx.tw.append(f'tl.to("#{nid}g",{{x:-70,duration:{t1 - gt:.3f},ease:{json.dumps(fx.E["drift"])}}},RRM.q({gt:.4f}));')
    lab = ""
    if a.get("label"):
        tl_ = _when(cx, beat, a.get("label_at"), 0.12)
        fx.text_in(cx, beat, f"#{nid}l", tl_, "mono")
        lab = (f'<div class="mono lbl" id="{nid}l" {cx.box("text", max(tl_, t0), t1, True)}>{esc(a["label"])}</div>'
               + _rule(cx, beat, f"{nid}k", a["label"], tl_, t1))
    tc = _when(cx, beat, a.get("circle_at"), 0.25)
    _draw(cx, beat, f"#{nid}c path", max(tc, tn + 0.2), 0.55)
    if a.get("circle_sfx"):
        cx.event(tc, a["circle_sfx"], f"circle {a['n']}")
    cy_ = 60 + size * 0.43
    d = _scribble_path(540, cy_, size * 0.42, size * 0.47, seed=a.get("seed", 5))
    title = ""
    if a.get("title"):
        tt = _when(cx, beat, a.get("title_at"), 0.3)
        fx.text_in(cx, beat, f"#{nid}t", tt, a.get("title_font", "serif"), None, len(a["title"]))
        fx.focus(cx, beat, tt, top + 60 + size * 0.86 + 70)
        cx.event(tt, a.get("title_sfx", "whoosh"), f"numeral title {a['title']}")
        title = (f'<div class="nut {a.get("title_font", "serif")}" id="{nid}t" style="top:{60 + size * 0.86 + 10:.0f}px" '
                 f'data-fit="940,40" {cx.box("text", max(tt, t0), t1, True)}>{esc(a["title"])}</div>')
    return (f'<div class="nuw" id="{nid}" style="top:{top}px;height:{h:.0f}px">{ghost}{lab}'
            f'<div class="nun" id="{nid}n" style="top:60px;font-size:{size}px;height:{size * 0.86:.0f}px;line-height:{size * 0.86:.0f}px" '
            f'{cx.box("glyph", max(tn, t0), t1, True)}>{esc(a["n"])}</div>'
            f'<svg class="circ" id="{nid}c" viewBox="0 0 1080 {h:.0f}" style="height:{h:.0f}px"><path d="{d}" pathLength="1" '
            f'stroke-dasharray="1" stroke-dashoffset="1"/></svg>{title}</div>')


def cred_stack(cx, beat, a):
    """items: [{text, at, font}] -> 01 / 02 / 03 lines: the index pops, the line rises letter by letter, its hairline
    draws across; the label tracks in over a drawn kicker rule."""
    sid, t0, t1 = cx.uid("cs"), beat["t0"], beat["t1"]
    items = a["items"]
    rh = a.get("row_h", 150)
    h = 70 + rh * len(items)
    top = _top(a, h)
    rows = []
    last_t = t0
    if a.get("label"):
        fx.text_in(cx, beat, f"#{sid}k", t0, "mono")
        rows.append(f'<div class="mono lbl" id="{sid}k" style="position:absolute;left:0;right:0;top:0;text-align:center" '
                    f'{cx.box("text", t0, t1, True)}>{esc(a["label"])}</div>'
                    + f'<div style="position:absolute;left:-110px;top:0;width:1080px">{_rule(cx, beat, sid + "r", a["label"], t0, t1)}</div>')
    for i, it in enumerate(items):
        rid = f"{sid}r{i}"
        t = _when(cx, beat, it.get("at"), 0.14 * i if it.get("at") is None else 0.0)
        fnt = it.get("font", "sans" if i % 2 == 0 else "serif")
        fx.enter(cx, beat, f"#{rid}i", t, "pop", **{"from": 0.3})
        fx.text_in(cx, beat, f"#{rid}t", t + 0.04, fnt, None, len(it["text"]))
        fx.grow_x(cx, beat, f"#{rid}h", t + 0.1, 0.6)
        fx.focus(cx, beat, t, 0 if top is None else top + 70 + i * rh + rh / 2, 0.8)
        if it.get("at") is not None:
            cx.event(t, "click", f"cred {it['text']}")
        if i and fx.live(cx, beat, t):     # reading focus: the earlier lines step back while the new one lands
            for j in range(i):
                cx.tw.append(f'tl.to("#{sid}r{j}",{{opacity:.3,duration:0.3,ease:{json.dumps(fx.E["snap"])}}},RRM.q({t:.4f}));')
            fx.moving(cx, beat, t, t + 0.3)
        last_t = t
        rows.append(f'<div class="csr" id="{rid}" style="top:{70 + i * rh}px;height:{rh}px">'
                    f'<span class="mono idx" id="{rid}i">{i + 1:02d}</span>'
                    f'<span class="cst {fnt}" id="{rid}t" data-fit="760,40" '
                    f'{cx.box("text", max(t, t0), t1, True)}>{esc(it["text"])}</span><span class="csl" id="{rid}h" '
                    f'{cx.box("card", max(t, t0), t1)}></span></div>')
    tr = _when(cx, beat, a["recap_at"], 1.2) if a.get("recap_at") else last_t + 1.3
    if len(items) > 1 and fx.live(cx, beat, tr) and tr < t1 - 0.3:   # recap: the whole stack lights back up
        cx.tw.append(f'tl.to({json.dumps([f"#{sid}r{j}" for j in range(len(items) - 1)])},{{opacity:1,duration:0.36,'
                     f'stagger:0.08,ease:{json.dumps(fx.E["snap"])}}},RRM.q({tr:.4f}));')
        fx.moving(cx, beat, tr, tr + 0.5)
    return f'<div class="csw" id="{sid}" style="top:{top}px;height:{h}px">{"".join(rows)}</div>'


def lab_report(cx, beat, a):
    """Paper lab report. rows: [{test, note, at}] ; title ; zoom: {row, at|null(instant), scale} ; circle: {row, at}
    The sheet flies in tilted and lands; each row wipes in on its word, its result bar fills, the camera follows."""
    rid, t0, t1 = cx.uid("lr"), beat["t0"], beat["t1"]
    rows = a["rows"]
    W, rh = a.get("w", 900), a.get("row_h", 84)
    H = 210 + rh * len(rows) + 56
    top = _top(a, H)
    left = (1080 - W) // 2
    t_in = beat.get("anchor_t0", t0)
    _land(cx, beat, f"#{rid}", t_in, a.get("enter", "sheet"))
    fx.text_in(cx, beat, f"#{rid}ti", t_in + 0.3, "serif", None, len(a.get("title", "Comprehensive panel")))
    if a.get("enter_sfx"):
        cx.event(t_in, a["enter_sfx"], "lab report in")
    body = []
    for i, r in enumerate(rows):
        t = _when(cx, beat, r.get("at"), 0.0)
        if r.get("at") is not None:
            fx.enter(cx, beat, f"#{rid}r{i}", t, "wipe", dir="left", dur=0.3)
            fx.grow_x(cx, beat, f"#{rid}b{i}", t + 0.22, 0.55, to=round(0.42 + 0.5 * ((i * 37 + 11) % 10) / 10, 2))
            fx.focus(cx, beat, t, top + 210 + i * rh + rh / 2, 0.7)
            cx.event(t, "tick", f"lab row {r['test']}")
        mark = ""
        if r.get("mark"):                # highlighter wipes across the row's test name (the one that matters)
            fx.grow_x(cx, beat, f"#{rid}m{i}", t + 0.35, 0.4)
            mark = f'<span class="mark" id="{rid}m{i}"></span>'
        body.append(f'<div class="lrr" id="{rid}r{i}" style="top:{210 + i * rh}px;height:{rh}px">'
                    f'<span class="lrt"><span class="klw">{mark}<span {cx.box("text", max(t, t0), t1, True)}>{esc(r["test"])}</span></span></span>'
                    f'<span class="lrn mono">{esc(r.get("note", ""))}</span><span class="lrv"><i id="{rid}b{i}"></i></span></div>')
    circ = ""
    if a.get("circle"):
        c = a["circle"]
        tc = _when(cx, beat, c.get("at"), 0.4)
        _draw(cx, beat, f"#{rid}c path", tc, 0.6)
        cx.event(tc, "scribble", "circle lab row")
        ry = 210 + c["row"] * rh + rh / 2
        d = _scribble_path(c.get("cx", 215), ry, c.get("rx", 205), c.get("ry", 60), seed=c.get("seed", 9), tilt=-3)
        circ = (f'<svg class="circ lrc" id="{rid}c" viewBox="0 0 {W} {H}" style="width:{W}px;height:{H}px">'
                f'<path d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>')
    zoom = a.get("zoom")
    wrap_style = f"left:{left}px;top:{top}px;width:{W}px;height:{H}px;rotate:{a.get('rot', -1.6)}deg"
    if zoom:
        wrap_style += ";box-shadow:0 40px 80px rgba(29,18,20,.18),0 8px 22px rgba(29,18,20,.10)"
        zr = zoom["row"]
        oy = 210 + zr * rh + rh / 2
        sc = zoom.get("scale", 1.7)
        dy = round(H * zoom.get("center", 0.5) - oy)
        z = {"scale": sc, "y": dy, "transformOrigin": f"44px {oy:.0f}px"}
        if zoom.get("at") is None:
            cx.init.append(f'gsap.set("#{rid}z",{json.dumps(z)});')
        else:
            tz = _when(cx, beat, zoom["at"], 0.0)
            cx.to(f"#{rid}z", tz, z, dur=0.6, ease=fx.E["camera"])
        wrap_style += ";overflow:hidden;border-radius:10px"
    head = (f'<div class="lrh"><span class="mono">{esc(a.get("kicker", "LAB REPORT"))}</span>'
            f'<span class="mono soft">{esc(a.get("kicker2", "FASTING  ·  8 AM"))}</span></div>'
            f'<div class="lrtitle serif" id="{rid}ti" {cx.box("text", t0, t1, True)}>{esc(a.get("title", "Comprehensive panel"))}</div>'
            f'<div class="lrcols mono"><span>TEST</span><span>NOTE</span><span>RESULT</span></div>')
    return (f'<div class="lrw" id="{rid}" style="{wrap_style}" {cx.box("card", t0, t1)}><div class="lrz" id="{rid}z">'
            f'<div class="paper">{head}{"".join(body)}<div class="lrfoot mono">REF RANGES ON FILE  ·  PAGE 1 OF 1</div></div>{circ}</div></div>')


def _odometer(value, size):
    """'7' -> a digit column 0..7 inside a mask (rolls up on its word). Non-integers stay plain text."""
    if not str(value).isdigit() or len(str(value)) > 2:
        return None, 0
    n = int(value)
    lh = round(size * 0.8)
    digits = "".join(f"<span style='height:{lh}px'>{k}</span>" for k in range(n + 1))
    return f'<span class="odo" style="height:{lh}px"><span class="col">{digits}</span></span>', n


def big_stat(cx, beat, a):
    """label (serif or mono), pre (serif italic, smears in on its word), value (giant sans: an integer ROLLS up like a
    counter and lands with a squash, anything else stamps), tag {text, at} pops, a hand-drawn underline draws."""
    sid, t0, t1 = cx.uid("bs"), beat["t0"], beat["t1"]
    size = a.get("size", 470)
    lh = 140 if a.get("label_style") == "serif" else 70
    h = lh + size * 0.8 + (120 if a.get("tag") else 0)
    top = _top(a, h)
    t_in = beat.get("anchor_t0", t0)
    serif = a.get("label_style") == "serif"
    fx.text_in(cx, beat, f"#{sid}l", t_in, "serif" if serif else "mono", None, len(a.get("label", "")))
    lcls = "bsl serif" if serif else "mono lbl"
    parts = [f'<div class="{lcls}" id="{sid}l" style="position:absolute;left:0;right:0;top:{20 if serif else 0}px;text-align:center" '
             f'{cx.box("text", t0, t1, True)}>{esc(a.get("label", ""))}</div>']
    vt = _when(cx, beat, a.get("at"), 0.0)
    odo, n = _odometer(a["value"], size)
    if odo:
        fx.enter(cx, beat, f"#{sid}v", vt - 0.02, "blurIn", y=0, scale=1.25, blur=12, dur=0.3)
        end = fx.roll(cx, beat, f"#{sid}v .col", vt, n, round(size * 0.8), 0.6)
        fx.squash(cx, beat, f"#{sid}v", end - 0.12, k=0.9)
    else:
        _land(cx, beat, f"#{sid}v", vt, "slam")
    fx.focus(cx, beat, vt, top + lh + size * 0.4)
    cx.event(vt, "thud", f"big stat {a['value']}")
    pre = ""
    if a.get("pre"):
        pt = _when(cx, beat, a.get("pre_at"), 0.0)
        _land(cx, beat, f"#{sid}p", pt, "slide")
        pre = (f'<span class="bsp serif" id="{sid}p" style="font-size:{round(size * 0.36)}px" '
               f'{cx.box("text", max(pt, t0), t1, True)}>{esc(a["pre"])}</span>')
    parts.append(f'<div class="bsr" style="top:{lh}px;height:{size * 0.8:.0f}px">{pre}<span class="bsv" id="{sid}v" '
                 f'style="font-size:{size}px;line-height:{size * 0.8:.0f}px" {cx.box("glyph", max(vt, t0), t1, True)}>'
                 f'{odo or esc(a["value"])}</span></div>')
    uy = lh + size * 0.8 + 8
    _draw(cx, beat, f"#{sid}u path", vt + 0.55, 0.4)
    parts.append(f'<svg class="sw" id="{sid}u" viewBox="0 0 1080 {uy + 40:.0f}" style="top:0;height:{uy + 40:.0f}px">'
                 f'<path d="M{620},{uy + 6:.0f} C700,{uy - 10:.0f} 780,{uy + 18:.0f} 860,{uy:.0f}" pathLength="1" '
                 f'stroke-dasharray="1" stroke-dashoffset="1"/></svg>')
    if a.get("tag"):
        tg = a["tag"]
        tt = _when(cx, beat, tg.get("at"), 1.0)
        _land(cx, beat, f"#{sid}g", tt, "pop")
        fx.focus(cx, beat, tt, top + lh + size * 0.8 + 60, 0.6)
        cx.event(tt, "pop", f"big stat tag {tg['text']}")
        parts.append(f'<div class="bstag" id="{sid}g" style="top:{lh + size * 0.8 + 30:.0f}px" '
                     f'{cx.box("text", max(tt, t0), t1, True)}><span>{esc(tg["text"])}</span></div>')
    return f'<div class="bsw" id="{sid}" style="top:{top}px;height:{h:.0f}px">{"".join(parts)}</div>'


def gauge(cx, beat, a):
    """label, left, right, needle: {from, to (0..1), at}, mark (text under the dial, on its word).
    The dial draws on segment by segment, the needle sweeps up to its first reading and hunts around it, swings on
    its word with an elastic settle, then keeps reading live."""
    gid, t0, t1 = cx.uid("ga"), beat["t0"], beat["t1"]
    R = a.get("r", 380)
    h = 70 + R + 150
    top = _top(a, h)
    t_in = beat.get("anchor_t0", t0)
    lbl = a.get("label", "")
    fx.text_in(cx, beat, f"#{gid}l", t_in, "mono")
    nd = a.get("needle", {})
    f0, f1 = nd.get("from", 0.18), nd.get("to", 0.86)
    tn = _when(cx, beat, nd.get("at"), 1.0)
    rot = lambda v: -90 + 180 * v  # noqa: E731
    live = fx.live(cx, beat, t_in)
    cx.init.append(f'gsap.set("#{gid}n",{{rotation:{rot(0.0 if live else f0):.1f},svgOrigin:"540 {70 + R}"}});')
    if live:
        cx.to(f"#{gid}n", t_in + 0.95, {"rotation": rot(f0)}, dur=0.8, ease=fx.E["glide"])
        cx.to(f"#{gid}v", t_in + 0.95, {"strokeDashoffset": round(1 - f0, 4)}, dur=0.8, ease=fx.E["glide"])
        fx.moving(cx, beat, t_in + 0.95, t_in + 1.75)
        fx.jitter(cx, beat, f"#{gid}n", t_in + 1.8, tn - 0.05, rot(f0), amp=3.2, step=0.26, arc=f"#{gid}v")
    cx.to(f"#{gid}n", tn, {"rotation": rot(f1)}, dur=0.9, ease=fx.E["wobble"])
    cx.to(f"#{gid}v", tn, {"strokeDashoffset": round(1 - f1, 4)}, dur=0.9, ease=fx.E["wobble"])
    cx.init.append(f'gsap.set("#{gid}v",{{strokeDashoffset:{1 if live else round(1 - f0, 4)}}});')
    fx.moving(cx, beat, tn, tn + 0.9)
    fx.jitter(cx, beat, f"#{gid}n", tn + 0.95, t1, rot(f1), amp=2.6, step=0.2, seed=9, arc=f"#{gid}v")
    fx.focus(cx, beat, tn, top + 70 + R * 0.6)
    cx.event(tn, "whoosh", "gauge needle")
    if f1 >= 2 / 3:                      # the needle lands in the red: that zone lights up and its end label pops
        tp = tn + 0.3
        cx.tw.append(f'tl.to("#{gid}s2",{{attr:{{"stroke-width":84}},duration:0.16,ease:{json.dumps(fx.E["snap"])}}},RRM.q({tp:.4f}));')
        cx.tw.append(f'tl.to("#{gid}s2",{{attr:{{"stroke-width":64}},duration:0.5,ease:{json.dumps(fx.E["wobble"])}}},RRM.q({tp + 0.16:.4f}));')
        cx.tw.append(f'tl.to("#{gid}e1",{{scale:1.35,color:"var(--accent)",duration:0.2,ease:{json.dumps(fx.E["pop"])}}},RRM.q({tp:.4f}));')
        fx.moving(cx, beat, tp, tp + 0.66)
    cxp, cyp = 540, 70 + R
    segs = []
    cols = ["#C9BFB4", "#D9B45A", "var(--accent)"]
    for k in range(3):
        a0, a1 = math.pi + k * math.pi / 3 + 0.03, math.pi + (k + 1) * math.pi / 3 - 0.03
        x0, y0 = cxp + R * math.cos(a0), cyp + R * math.sin(a0)
        x1, y1 = cxp + R * math.cos(a1), cyp + R * math.sin(a1)
        segs.append(f'<path id="{gid}s{k}" d="M{x0:.1f},{y0:.1f} A{R},{R} 0 0 1 {x1:.1f},{y1:.1f}" stroke="{cols[k]}" '
                    f'stroke-width="58" fill="none" stroke-linecap="butt" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>')
        _draw(cx, beat, f"#{gid}s{k}", t_in + 0.08 + 0.3 * k, 0.42)
    ticks = "".join(
        f'<line x1="{cxp + (R - 60) * math.cos(math.pi + i * math.pi / 10):.1f}" y1="{cyp + (R - 60) * math.sin(math.pi + i * math.pi / 10):.1f}" '
        f'x2="{cxp + (R - 46) * math.cos(math.pi + i * math.pi / 10):.1f}" y2="{cyp + (R - 46) * math.sin(math.pi + i * math.pi / 10):.1f}" '
        f'stroke="rgba(29,18,20,.35)" stroke-width="3"/>' for i in range(11))
    fx.enter(cx, beat, f"#{gid}tk", t_in + 0.7, "blurIn", y=0, scale=0.86, blur=8, dur=0.5)
    rv = R - 104                         # the value arc: a thin inner ring that fills behind the needle
    varc = (f'<path id="{gid}v" d="M{cxp - rv},{cyp} A{rv},{rv} 0 0 1 {cxp + rv},{cyp}" stroke="var(--accent)" stroke-opacity=".55" '
            f'stroke-width="12" fill="none" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>')
    needle = varc + (f'<g id="{gid}n"><path d="M{cxp - 12},{cyp} L{cxp},{cyp - R + 70} L{cxp + 12},{cyp} Z" fill="var(--ink)"/>'
              f'<circle cx="{cxp}" cy="{cyp}" r="26" fill="var(--ink)"/><circle cx="{cxp}" cy="{cyp}" r="9" fill="var(--paperc)"/></g>')
    mark = ""
    if a.get("mark"):
        tm = _when(cx, beat, a.get("mark_at"), 1.2)
        fx.text_in(cx, beat, f"#{gid}m", tm, "serif", None, len(a["mark"]))
        fx.focus(cx, beat, tm, top + 70 + R + 100, 0.6)
        mark = (f'<div class="gam serif" id="{gid}m" style="top:{70 + R + 50}px" data-fit="900,40" '
                f'{cx.box("text", max(tm, t0), t1, True)}>{esc(a["mark"])}</div>')
    fx.text_in(cx, beat, f"#{gid}e0", t_in + 0.4, "mono")
    fx.text_in(cx, beat, f"#{gid}e1", t_in + 1.0, "mono")
    ends = (f'<div class="gae mono" id="{gid}e0" style="left:{cxp - R - 40}px;top:{cyp + 20}px" {cx.box("text", t0, t1, True)}>{esc(a.get("left", "LOW"))}</div>'
            f'<div class="gae mono r" id="{gid}e1" style="left:{cxp + R - 160}px;top:{cyp + 20}px" {cx.box("text", t0, t1, True)}>{esc(a.get("right", "HIGH"))}</div>')
    return (f'<div class="gaw" id="{gid}" style="top:{top}px;height:{h}px">'
            f'<div class="mono lbl" id="{gid}l" style="position:absolute;left:0;right:0;top:0;text-align:center" {cx.box("text", t0, t1, True)}>'
            f'{esc(lbl)}</div>{_rule(cx, beat, gid + "k", lbl, t_in, t1)}'
            f'<div style="position:absolute;left:{cxp - R - 29}px;top:{41}px;width:{2 * R + 58}px;height:{R + 29}px" {cx.box("card", t0, t1)}></div>'
            f'<svg viewBox="0 0 1080 {h}" style="position:absolute;left:0;top:0;width:1080px;height:{h}px">'
            f'{"".join(segs)}<g id="{gid}tk">{ticks}</g>{needle}</svg>{ends}{mark}</div>')


ICONS = {
    "plate": '<circle cx="50" cy="52" r="30" fill="none" stroke="currentColor" stroke-width="6"/><circle cx="50" cy="52" r="17" fill="none" stroke="currentColor" stroke-width="4"/>'
             '<path d="M12 18v22M8 18v14q0 8 4 8M16 18v14q0 8-4 8M88 18q-10 8-6 26h6v26" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>',
    "dumbbell": '<path d="M24 50h52" stroke="currentColor" stroke-width="8" stroke-linecap="round"/><rect x="12" y="30" width="14" height="40" rx="5" fill="currentColor"/>'
                '<rect x="74" y="30" width="14" height="40" rx="5" fill="currentColor"/><rect x="4" y="38" width="8" height="24" rx="3" fill="currentColor"/>'
                '<rect x="88" y="38" width="8" height="24" rx="3" fill="currentColor"/>',
    "drop": '<path d="M50 12C38 32 26 46 26 60a24 24 0 0048 0C74 46 62 32 50 12z" fill="currentColor"/>',
    "flask": '<path d="M40 12h20M44 12v26L22 80a6 6 0 005 9h46a6 6 0 005-9L56 38V12" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/><path d="M30 66h40l7 14H23z" fill="currentColor"/>',
    "calendar": '<rect x="14" y="20" width="72" height="66" rx="10" fill="none" stroke="currentColor" stroke-width="6"/><path d="M14 40h72M32 12v16M68 12v16" stroke="currentColor" stroke-width="6" stroke-linecap="round"/>',
    "heart": '<path d="M50 84S14 62 14 38a18 18 0 0136-6 18 18 0 0136 6c0 24-36 46-36 46z" fill="currentColor"/>',
}


def tiles(cx, beat, a):
    """heading {text, at, font}, items: [{icon, label, at, tone: accent|ink|gold}]
    Tiles DROP in on their words (fall, squash on landing, elastic settle), then float out of phase; the heading
    rises letter by letter."""
    tid, t0, t1 = cx.uid("ti"), beat["t0"], beat["t1"]
    items = a["items"]
    S, gap = a.get("size", 330), 60
    hh = 150 if a.get("heading") else 0
    h = hh + S + 90
    top = _top(a, h)
    parts = []
    if a.get("heading"):
        hd = a["heading"]
        th = _when(cx, beat, hd.get("at"), 0.0)
        fx.text_in(cx, beat, f"#{tid}h", th, hd.get("font", "serif"), None, len(hd["text"]))
        parts.append(f'<div class="tih {hd.get("font", "serif")}" id="{tid}h" data-fit="960,40" {cx.box("text", max(th, t0), t1, True)}>'
                     f'{esc(hd["text"])}</div>')
    W = len(items) * S + (len(items) - 1) * gap
    x0 = (1080 - W) // 2
    for i, it in enumerate(items):
        iid = f"{tid}i{i}"
        t = _when(cx, beat, it.get("at"), 0.3 * i)
        end = _land(cx, beat, f"#{iid}", t, "drop")
        fx.bob(cx, beat, f"#{iid} svg", end + 0.05 + 0.3 * i, t1, amp=8, period=1.1)
        fx.focus(cx, beat, t, top + hh + S / 2, 0.6)
        cx.event(t, "pop", f"tile {it['label']}")
        parts.append(f'<div class="tile {it.get("tone", "accent")}" id="{iid}" style="left:{x0 + i * (S + gap)}px;top:{hh}px;width:{S}px;height:{S}px" '
                     f'{cx.box("card", max(t, t0), t1)}>'
                     f'<svg viewBox="0 0 100 100" width="{S * 0.46:.0f}" height="{S * 0.46:.0f}">{ICONS.get(it.get("icon", "heart"), ICONS["heart"])}</svg>'
                     f'<div class="til" {cx.box("text", max(t, t0), t1, True)}>{esc(it["label"])}</div></div>')
    return f'<div class="tiw" id="{tid}" style="top:{top}px;height:{h}px">{"".join(parts)}</div>'


def cal_flip(cx, beat, a):
    """page1 {top, big}, page2 {top, big}, flip_at, kicker (mono, over a drawn kicker rule), circle on page 2.
    The pad drops onto the paper and settles, page 1's word stamps, the page tears up and over on its word, page 2's
    word rises letter by letter and the hand-drawn circle closes around it."""
    cid, t0, t1 = cx.uid("cf"), beat["t0"], beat["t1"]
    W, H = a.get("w", 640), a.get("h", 600)
    top = _top(a, H + 70)
    left = (1080 - W) // 2
    p1, p2 = a.get("page1", {}), a.get("page2", {})
    t_in = beat.get("anchor_t0", t0)
    end = _land(cx, beat, f"#{cid}s", t_in, "drop")
    fx.text_in(cx, beat, f"#{cid}p1b", min(end, t_in + 0.45), p1.get("font", "sans"), "slam")
    tf = _when(cx, beat, a.get("flip_at"), 1.0)
    cx.set(f"#{cid}p1", t0, {"rotationX": 0, "transformPerspective": 1600, "transformOrigin": "50% 0%"})
    cx.to(f"#{cid}p1", tf, {"rotationX": -100, "opacity": 0}, dur=0.3, ease=fx.E["exit"])
    fx.moving(cx, beat, tf, tf + 0.3)
    fx.focus(cx, beat, tf, top + 70 + H / 2, 0.8)
    cx.event(tf, "flip", "calendar flip")
    fx.text_in(cx, beat, f"#{cid}p2b", tf + 0.12, p2.get("font", "sans"), None, len(p2.get("big", "")))
    tc = tf + 0.3
    _draw(cx, beat, f"#{cid}c path", tc, 0.4)
    d = _scribble_path(W / 2, 110 + (H - 110) / 2 - 8, W * 0.44, 118, seed=a.get("seed", 21), tilt=-4)

    def page(pid, p, extra="", span=(t0, t1)):
        return (f'<div class="calp" id="{pid}" style="width:{W}px;height:{H}px"><div class="calh mono">{esc(p.get("top", ""))}</div>'
                f'<div class="calb {p.get("font", "sans")}" id="{pid}b" data-fit="{W - 60},40" {cx.box("text", span[0], span[1], True)}>'
                f'{esc(p.get("big", ""))}</div>'
                f'<div class="cals mono">{esc(p.get("small", ""))}</div>{extra}</div>')
    circ = (f'<svg class="circ" id="{cid}c" viewBox="0 0 {W} {H}" style="width:{W}px;height:{H}px;left:0;top:0">'
            f'<path d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>')
    kick = ""
    if a.get("kicker"):
        fx.text_in(cx, beat, f"#{cid}k", t_in + 0.1, "mono")
        kick = (f'<div class="mono lbl" id="{cid}k" style="position:absolute;left:0;right:0;top:0;text-align:center" '
                f'{cx.box("text", t0, t1, True)}>{esc(a["kicker"])}</div>' + _rule(cx, beat, cid + "r", a["kicker"], t_in + 0.1, t1))
    rings = "".join(f'<div class="ring" style="left:{x}px"></div>' for x in (110, W - 140))
    return (f'<div class="cfw" id="{cid}" style="top:{top}px;height:{H + 70}px">{kick}'
            f'<div class="calstack" id="{cid}s" style="left:{left}px;top:70px;width:{W}px;height:{H}px" {cx.box("card", t0, t1)}>'
            f'<div class="calunder"></div>{page(cid + "p2", p2, circ, (tf, t1))}{page(cid + "p1", p1, "", (t0, tf))}{rings}</div></div>')


def lab_focus(cx, beat, a):
    """One lab-report line, magnified: faded line above, the hero test huge, its note, an empty result box,
    and a hand-drawn circle around the test on its word. args: test, note, prev, prev_note, line, circle_at
    The sheet flies in and lands, the test stamps in letter by letter, the note tracks in, a light keeps sweeping
    the empty result box (a result on its way) until the beat ends."""
    fid, t0, t1 = cx.uid("lf"), beat["t0"], beat["t1"]
    W, H = a.get("w", 880), a.get("h", 600)
    top = _top(a, H)
    left = (1080 - W) // 2
    t_in = beat.get("anchor_t0", t0)
    _land(cx, beat, f"#{fid}", t_in, "sheet")
    fx.enter(cx, beat, f"#{fid}p", t_in + 0.2, "blurIn", y=-20, scale=1, blur=8, dur=0.36)
    fx.enter(cx, beat, f"#{fid}t", t_in + 0.32, "letterStamp", stagger=0.04)
    fx.text_in(cx, beat, f"#{fid}n", t_in + 0.8, "mono")
    fx.focus(cx, beat, t_in + 0.4, top + 300, 0.5)
    fx.sweep(cx, beat, f"#{fid}w", t_in + 1.0, t1, every=0.9, dur=0.6)
    tz = t_in + 0.95                     # the camera leans into the line: the sheet magnifies toward the test
    if fx.live(cx, beat, t_in) and tz < t1 - 1.0:
        cx.init.append(f'gsap.set("#{fid}",{{transformOrigin:"50% {300 / H * 100:.0f}%"}});')
        cx.tw.append(f'tl.to("#{fid}",{{scale:1.08,rotation:{a.get("rot", -1.2) * -1:.2f},y:-24,duration:0.75,ease:{json.dumps(fx.E["camera"])}}},RRM.q({tz:.4f}));')
        fx.moving(cx, beat, tz, tz + 0.75)
    tc = _when(cx, beat, a.get("circle_at"), 0.6)
    _draw(cx, beat, f"#{fid}c path", max(tc, t_in + 0.9), 0.6)
    fx.focus(cx, beat, tc, top + 300, 0.8)
    cx.event(tc, "scribble", "circle lab row")
    stamp = ""
    if a.get("stamp"):                   # an ink stamp hits the sheet on its word ("must be on it")
        st = a["stamp"]
        ts = _when(cx, beat, st.get("at"), 1.4)
        _land(cx, beat, f"#{fid}s", ts, "slam")
        fx.focus(cx, beat, ts, top + H - 120, 0.6)
        cx.event(ts, "thud", f"lab stamp {st['text']}")
        stamp = (f'<div class="lfs mono" id="{fid}s" {cx.box("text", max(ts, t0), t1, True)}>'
                 f'<span>{esc(st["text"])}</span></div>')
    hy = 300
    d = _scribble_path(a.get("cx", 440), hy, a.get("rx", 420), a.get("ry", 80), seed=a.get("seed", 9), tilt=-2)
    return (f'<div class="lfw" id="{fid}" style="left:{left}px;top:{top}px;width:{W}px;height:{H}px;rotate:{a.get("rot", -1.2)}deg" '
            f'{cx.box("card", t0, t1)}><div class="paper"></div>'
            f'<div class="lrh"><span class="mono">{esc(a.get("kicker", "LAB REPORT"))}</span>'
            f'<span class="mono soft">{esc(a.get("line", "LINE 05"))}</span></div>'
            f'<div class="lfp" id="{fid}p"><span class="lfpt">{esc(a.get("prev", ""))}</span><span class="mono">{esc(a.get("prev_note", ""))}</span></div>'
            f'<div class="lft" id="{fid}t" style="top:{hy - 62}px" data-fit="{W - 120},40" {cx.box("text", t0, t1, True)}>{esc(a["test"])}</div>'
            f'<div class="lfn mono" id="{fid}n" style="top:{hy + 100}px" {cx.box("text", t0, t1, True)}>{esc(a.get("note", ""))}</div>'
            f'<div class="lfr"><span class="mono">RESULT</span><span class="lfbox"><i class="sweep" id="{fid}w"></i></span></div>'
            f'<svg class="circ" id="{fid}c" viewBox="0 0 {W} {H}" style="width:{W}px;height:{H}px;left:0;top:0">'
            f'<path d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>{stamp}</div>')


INSERTS = {"lab_focus": lab_focus, "kinetic": kinetic, "numeral": numeral, "cred_stack": cred_stack, "lab_report": lab_report,
           "big_stat": big_stat, "gauge": gauge, "tiles": tiles, "cal_flip": cal_flip,
           "media_stack": hook.media_stack, "title_card": hook.title_card, "cycle_chart": chart.cycle_chart}


def stage(cx, beats, placement, segs=None, mcfg=None, captions=None):
    """Style hook (split/compose.py): the stage camera on every graphic beat, the speaker card as a depth layer, and
    the one-word captions rolling out as the next word rolls in."""
    if mcfg and mcfg.get("level") == "polished" and _project_motion(cx).get("handheld") is None:
        mcfg["handheld"] = True      # this style's default: the speaker card is a live camera, never locked off
    fx.stage(cx, beats, placement, segs, mcfg)
    fx.caption_roll(cx, captions or [], mcfg)


def _project_motion(cx):
    try:
        with open(os.path.join(cx.dir, "project.json")) as f:
            m = json.load(f).get("motion")
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def font_setup(brand):
    """(italic families to fetch, fonts to wait for) from the brand: fonts.serif (default Instrument Serif) is the
    italic accent face, fonts.mono the label face. A project brand.json can swap them (e.g. Playfair Display)."""
    f = brand["fonts"]
    serif, mono = f.get("serif", DEFAULTS["fonts"]["serif"]), f.get("mono", DEFAULTS["fonts"]["mono"])
    return [serif], [f'italic 400 120px "{serif}"', f'400 120px "{serif}"', f'500 30px "{mono}"', f'700 30px "{mono}"']


# ----------------------------------------------------------------------------- captions
def word_cap_top(cx, c, layout):
    if layout == "card":
        return cx.card["top"] - cx.card.get("caption_band", 128) + 4
    if layout == "stage":
        return cx.stage_bottom + 40
    if layout == "split":
        return 990
    if layout == "media":  # B-roll plate: the beat says where the subject is not (args cap_y), default lower third
        b = next((x for x in getattr(cx, "beats", []) if x["t0"] - 1e-3 <= c["t0"] < x["t1"]), None)
        ys = [it.get("args", {}).get("cap_y") for it in (b or {}).get("items", []) if it.get("args", {}).get("cap_y")]
        return ys[0] if ys else 1300
    chin = cx.chin(c["t0"], c["t1"])
    return round(min(max(1250, (chin or 1200) + 30), 1330))


def css(brand, cx):
    c = brand["colors"]
    f = brand["fonts"]
    serif = f"'{f.get('serif', 'Instrument Serif')}',Georgia,serif"
    mono = f"'{f.get('mono', 'JetBrains Mono')}',ui-monospace,Menlo,monospace"
    return hook.css(brand) + chart.css(brand) + fx.CSS + f"""
:root{{--fs:{serif};--fm:{mono};--paperc:#FBF8F4;--hl:{c.get('highlight', c['accent2'])};
  --paper:radial-gradient(120% 80% at 50% 30%,#FDFBF8 0%,{c['bg']} 55%,color-mix(in srgb,{c['bg']} 88%,#8a7358) 100%);
  --cardshadow:0 -2px 0 rgba(255,255,255,.55),0 -14px 34px rgba(29,18,20,.16),0 -40px 90px rgba(29,18,20,.18),0 40px 90px rgba(29,18,20,.28)}}
.serif{{font-family:var(--fs);font-style:italic;font-weight:400}}
.mono{{font-family:var(--fm)}}
.mono.lbl{{font:700 28px/1 var(--fm);letter-spacing:.24em;text-transform:uppercase;color:color-mix(in srgb,var(--ink) 62%,transparent);white-space:nowrap}}
.soft{{color:color-mix(in srgb,var(--ink) 45%,transparent)}}
/* one-word captions */
.cap.wcap .pill{{background:none;padding:0;border-radius:0;font:800 96px/1.12 var(--fd);letter-spacing:-.03em;color:var(--ink)}}
.cap.wcap.acc .pill{{font:italic 400 124px/1 var(--fs);letter-spacing:-.01em;color:var(--accent)}}
.cap.wcap.wpill .pill{{background:rgba(29,18,20,.86);color:#F6F2EE;padding:14px 30px 16px;border-radius:20px;font-size:66px;line-height:1.05}}
.cap.wcap.wpill.acc .pill{{font:italic 400 82px/1 var(--fs);color:{c['accent2']};padding:12px 32px 18px}}
/* kinetic */
.kin{{position:absolute;left:0;width:1080px}}
.kl{{position:absolute;left:0;width:1080px;text-align:center;white-space:nowrap;display:flex;align-items:center;justify-content:center}}
.klw{{position:relative;display:inline-block;isolation:isolate;word-spacing:.06em}}
.klt{{display:inline-block}}
.kl.sans{{font-family:var(--fd);font-weight:900;letter-spacing:-.03em;word-spacing:.04em;line-height:1}}
.kl.serif{{font-family:var(--fs);font-style:italic;font-weight:400;letter-spacing:-.01em;line-height:1}}
.kl.mono{{font-family:var(--fm);font-weight:700;letter-spacing:.24em;text-transform:uppercase;line-height:1}}
.kl.ink{{color:var(--ink)}} .kl.accent{{color:var(--accent)}} .kl.gold{{color:{c['accent2']}}}
.kl.soft{{color:color-mix(in srgb,var(--ink) 58%,transparent)}}
.beat.fullb .kl.soft{{color:var(--ink);font-weight:800}}
.sw,.circ{{position:absolute;left:0;width:1080px;overflow:visible;pointer-events:none}}
.sw path{{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round}}
.circ path{{fill:none;stroke:var(--accent);stroke-width:9;stroke-linecap:round;stroke-linejoin:round}}
/* numeral */
.nug{{position:absolute;left:0;width:1080px;text-align:center;font-family:var(--fs);font-style:italic;color:transparent;
  -webkit-text-stroke:2.5px color-mix(in srgb,var(--accent) 16%,transparent);white-space:nowrap;padding-left:520px;box-sizing:border-box}}
.nuw{{position:absolute;left:0;width:1080px}}
.nuw .lbl{{position:absolute;left:0;right:0;top:0;text-align:center}}
.nun{{position:absolute;left:0;right:0;margin:0 auto;width:fit-content;text-align:center;font-family:var(--fs);font-style:italic;color:var(--ink);white-space:nowrap}}
.nut{{position:absolute;left:0;width:1080px;text-align:center;white-space:nowrap;font-size:120px;line-height:1;color:var(--accent)}}
.nut.sans{{font-family:var(--fd);font-weight:900;letter-spacing:-.04em;color:var(--ink)}}
/* credential stack */
.csw{{position:absolute;left:110px;width:860px}}
.csr{{position:absolute;left:0;right:0;display:flex;align-items:center;gap:34px}}
.csl{{position:absolute;left:0;right:0;bottom:0;height:2px;background:rgba(29,18,20,.16)}}
.csr .idx{{display:inline-block}}
.csr .idx{{font:700 30px/1 var(--fm);color:var(--accent);letter-spacing:.06em;width:54px}}
.cst{{white-space:nowrap;line-height:1}}
.cst.sans{{font:900 92px/1 var(--fd);letter-spacing:-.03em;color:var(--ink)}}
.cst.serif{{font:italic 400 108px/1 var(--fs);color:var(--accent)}}
/* lab report */
.lrw{{position:absolute}}
.lrz{{position:absolute;inset:0}}
.paper{{position:absolute;inset:0;background:var(--paperc);border-radius:10px;
  box-shadow:0 2px 0 rgba(255,255,255,.8) inset,0 40px 80px rgba(29,18,20,.18),0 8px 22px rgba(29,18,20,.10)}}
.lrh{{position:absolute;left:44px;right:44px;top:40px;display:flex;justify-content:space-between;font:700 22px/1 var(--fm);letter-spacing:.16em}}
.lrtitle{{position:absolute;left:44px;top:84px;font-size:70px;line-height:1;color:var(--ink);white-space:nowrap}}
.lrcols{{position:absolute;left:44px;right:44px;top:176px;display:grid;grid-template-columns:350px 1fr 120px;font:700 20px/1 var(--fm);
  letter-spacing:.18em;color:color-mix(in srgb,var(--ink) 50%,transparent);padding-bottom:10px;border-bottom:3px solid var(--ink)}}
.lrr{{position:absolute;left:44px;right:44px;display:grid;grid-template-columns:350px 1fr 120px;align-items:center;
  border-bottom:2px dashed rgba(29,18,20,.16)}}
.lrt{{font:800 50px/1 var(--fd);letter-spacing:-.02em;word-spacing:.04em;color:var(--ink);white-space:nowrap}}
.lrn{{font:500 22px/1.2 var(--fm);color:color-mix(in srgb,var(--ink) 55%,transparent)}}
.lrv{{height:16px;border-radius:8px;background:rgba(29,18,20,.10);overflow:hidden;position:relative}}
.lrv i{{position:absolute;left:0;top:0;bottom:0;width:100%;border-radius:8px;background:var(--accent)}}
.lrfoot{{position:absolute;left:44px;bottom:30px;font:500 18px/1 var(--fm);letter-spacing:.14em;color:color-mix(in srgb,var(--ink) 40%,transparent)}}
.lrc{{left:0;top:0}}
/* lab focus */
.lfw{{position:absolute}}
.lfp{{position:absolute;left:56px;right:56px;top:110px;height:70px;display:flex;justify-content:space-between;align-items:center;
  border-bottom:2px dashed rgba(29,18,20,.14)}}
.lfp > *{{opacity:.38}}
.lfpt{{font:800 50px/1 var(--fd);letter-spacing:-.02em;color:var(--ink)}}
.lfp .mono{{font:500 26px/1 var(--fm)}}
.lft{{position:absolute;left:56px;height:124px;display:flex;align-items:center;font:900 112px/1 var(--fd);letter-spacing:-.04em;
  color:var(--ink);white-space:nowrap}}
.lfn{{position:absolute;left:60px;font:700 32px/1 var(--fm);letter-spacing:.06em;color:var(--accent);white-space:nowrap}}
.lfr{{position:absolute;left:56px;right:56px;bottom:56px;display:flex;align-items:center;gap:24px;font:700 24px/1 var(--fm);
  letter-spacing:.2em;color:color-mix(in srgb,var(--ink) 50%,transparent)}}
.lfs{{position:absolute;right:46px;bottom:118px;rotate:-7deg;transform-origin:50% 50%}}
.lfs span{{display:inline-block;font:800 34px/1 var(--fm);letter-spacing:.16em;color:var(--accent);border:5px solid var(--accent);
  border-radius:12px;padding:14px 20px 12px;background:color-mix(in srgb,var(--paperc) 70%,transparent)}}
.lfbox{{flex:1;height:64px;border-radius:14px;border:3px dashed rgba(29,18,20,.22);position:relative;overflow:hidden}}
/* big stat */
.bsw{{position:absolute;left:0;width:1080px}}
.bsl{{font-size:104px;line-height:1;color:var(--accent);white-space:nowrap}}
.bsr{{position:absolute;left:0;width:1080px;display:flex;align-items:flex-end;justify-content:center;gap:26px}}
.bsp{{font-size:150px;line-height:1;color:var(--ink);padding-bottom:40px}}
.bsv{{font-family:var(--fd);font-weight:900;letter-spacing:-.06em;color:var(--accent);display:inline-block}}
.bstag{{position:absolute;left:0;width:1080px;display:flex;justify-content:center}}
.bstag span{{background:var(--ink);color:#F6F2EE;font:700 34px/1 var(--fm);letter-spacing:.12em;text-transform:uppercase;
  padding:20px 30px;border-radius:999px;white-space:nowrap}}
/* gauge */
.gaw{{position:absolute;left:0;width:1080px}}
.gae{{position:absolute;width:200px;font:700 24px/1 var(--fm);letter-spacing:.18em;color:color-mix(in srgb,var(--ink) 55%,transparent)}}
.gae.r{{text-align:right;transform-origin:100% 50%}}
.gam{{position:absolute;left:0;width:1080px;text-align:center;font-size:104px;line-height:1;color:var(--accent);white-space:nowrap}}
/* tiles */
.tiw{{position:absolute;left:0;width:1080px}}
.tih{{position:absolute;left:0;width:1080px;top:0;text-align:center;font-size:120px;line-height:1;color:var(--ink);white-space:nowrap}}
.tih.serif{{color:var(--accent)}}
.tile{{position:absolute;border-radius:76px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;
  box-shadow:0 34px 70px rgba(29,18,20,.22),0 8px 20px rgba(29,18,20,.10),inset 0 2px 0 rgba(255,255,255,.35)}}
.tile.accent{{background:linear-gradient(160deg,color-mix(in srgb,var(--accent) 82%,#fff) 0%,var(--accent) 60%);color:#F6F2EE}}
.tile.ink{{background:linear-gradient(160deg,#3a2a2d 0%,var(--ink) 60%);color:{c['accent2']}}}
.tile.gold{{background:linear-gradient(160deg,#f0d78f 0%,{c['accent2']} 60%);color:var(--ink)}}
.til{{font:800 40px/1 var(--fd);letter-spacing:-.02em;word-spacing:.04em;white-space:nowrap}}
/* calendar */
.cfw{{position:absolute;left:0;width:1080px}}
.calstack{{position:absolute}}
.calunder{{position:absolute;left:10px;right:-10px;top:14px;bottom:-14px;border-radius:26px;background:#E9E1D6;
  box-shadow:0 40px 80px rgba(29,18,20,.18)}}
.calp{{position:absolute;left:0;top:0;border-radius:26px;background:var(--paperc);overflow:hidden;
  box-shadow:0 10px 30px rgba(29,18,20,.12);backface-visibility:hidden}}
.calh{{height:110px;background:var(--accent);color:#F6F2EE;display:flex;align-items:center;justify-content:center;
  font:700 30px/1 var(--fm);letter-spacing:.3em}}
.calb{{position:absolute;left:0;right:0;top:110px;bottom:70px;display:flex;align-items:center;justify-content:center;white-space:nowrap;color:var(--ink)}}
.calb.sans{{font:900 230px/1 var(--fd);letter-spacing:-.03em;word-spacing:.05em}}
.calb.serif{{font:italic 400 150px/1 var(--fs);color:var(--accent)}}
.cals{{position:absolute;left:0;right:0;bottom:36px;text-align:center;font:700 24px/1 var(--fm);letter-spacing:.22em;
  color:color-mix(in srgb,var(--ink) 50%,transparent)}}
.ring{{position:absolute;top:-22px;width:30px;height:60px;border-radius:15px;background:linear-gradient(90deg,#8d8178,#d8cfc6 50%,#8d8178);
  box-shadow:0 4px 8px rgba(0,0,0,.25)}}
"""
