"""deck_inserts.py: split-deck panel inserts with motion that carries meaning (Motion v2 phase 3).

Same args as the plain inserts (inserts.py / overlay.py), so an edl written for the split deck keeps working; when the
deck camera is on (deck.py) compose swaps these in. What changes:
  hook_card   card lands on the cut, the second line pushes through its mask on its word, an underline draws, the
              leading number stamps on its word, the deck camera pushes to it
  checklist   bigger rows stagger in; each tick pops with a ring burst, a highlight sweep, a progress bar fill and a
              rolling n/N counter; the camera glides to the ticked row
  table       rows blur in from the right on their words, a selection bar follows the newest row, the camera follows
  number      the numeral stamps on the cut, the title letters rise on its word, a step bar (args.of) fills
  stat        the value rolls like an odometer onto its word, a zone meter draws and its marker slides past the line
  name_card   bigger credential card, the accent bar draws, the role smears in on its word with a tick
  prompt      (new) a search / prompt bar: focus ring, the text types on the words, a result chip drops in
Every time is a word ('@word') or seconds after the beat start; visuals land a frame before the word.
"""
import json
import re

import deck
import inserts
import overlay
from ctx import esc, snap

E = {"snap": "expo.out", "glide": "power4.out", "land": "back.out(1.4)", "pop": "back.out(2.2)", "stamp": "power4.out",
     "whip": "expo.inOut", "draw": "power2.inOut", "exit": "power3.in", "wobble": "elastic.out(1,0.45)"}
LEAD = 0.04


def at(cx, beat, spec, default=0.0):
    """Word-anchored time with the visual lead (never before the beat)."""
    t = cx.when(spec, beat, default)
    if isinstance(spec, str) and spec.startswith("@"):
        t -= LEAD
    return max(beat["t0"], t)


def word_at(cx, t):
    w = min(cx.words.w, key=lambda x: abs(x["start"] - t), default=None)
    return w["n"] if w and abs(w["start"] - t) < 0.2 else None


def ft(cx, sel, t, frm, to, dur=0.36, ease=E["snap"]):
    """fromTo that never shows its from-state before t (the element's resting CSS state shows until then)."""
    v = dict(to, duration=dur, ease=ease, immediateRender=False)
    cx.tw.append(f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(v)},{snap(t)});")


def hide(cx, sel):
    cx.init.append(f"gsap.set({json.dumps(sel)},{{autoAlpha:0}});")


def blur_in(cx, beat, sel, t, y=40, x=0, scale=0.94, blur=12, dur=0.42, ease=E["snap"], o0=0.0):
    cx.enter(beat, sel, t, {"opacity": o0, "x": x, "y": y, "scale": scale, "filter": f"blur({blur}px)"},
             {"opacity": 1, "x": 0, "y": 0, "scale": 1, "filter": "blur(0px)"}, dur=dur, ease=ease)


def accent(cx, t):
    w = word_at(cx, t + LEAD)
    if w and w not in cx.deck_accents:
        cx.deck_accents.append(w)


# ---------------------------------------------------------------------------------------------- hook
def hook_card(cx, beat, a):
    l1, l2 = a.get("l1") or cx.hook.get("l1", ""), a.get("l2") or cx.hook.get("l2", "")
    gid, t0, t1 = cx.uid("hk"), beat["t0"], beat["t1"]
    a0 = beat.get("anchor_t0", t0)
    m = re.match(r"^(\d+)(.*)$", l1)
    l1h = f'<b class="hkn" id="{gid}n">{esc(m.group(1))}</b>{esc(m.group(2))}' if m else esc(l1)
    # readable on frame 0 (the thumbnail): the card is already there and settles, line 1 included
    ft(cx, f"#{gid}", a0, {"scale": 1.06}, {"scale": 1}, 0.45, E["snap"])
    t2 = at(cx, beat, a.get("l2_at", "@get"), 0.5)
    hide(cx, f"#{gid}b")
    cx.tw.append(f"RRM.enter('maskPush',tl,'#{gid}b',{snap(t2)},{{dur:0.34}});")
    tu = at(cx, beat, a.get("line_at", "@fast"), 1.3)
    ft(cx, f"#{gid}u", tu, {"scaleX": 0}, {"scaleX": 1}, 0.5, E["whip"])
    cy = inserts.place({**a, "_alone": True}, 330) + 165 if "y" not in a else a["y"] + 165
    deck.focus(cx, beat, t2, 540, cy + 40, 1.05, "hook line 2")
    if m:
        sp = _spoken(m.group(1))
        dflt = f"@{sp}" if cx.words.find(sp, beat["t0"], beat["t1"]) is not None else f"@{m.group(1)}"
        tn = at(cx, beat, a.get("n_at", dflt), 2.8)
        ft(cx, f"#{gid}n", tn, {"scale": 1.8, "filter": "blur(10px)"}, {"scale": 1, "filter": "blur(0px)"}, 0.24, E["stamp"])
        deck.focus(cx, beat, tn, 400, cy - 50, 1.12, "hook number")
        deck.punch(cx, beat, tn + 0.05, 1.04, "hook number")
        cx.event(tn, "thud", "hook number")
        accent(cx, tn)
    cx.event(a0, "whoosh", "hook card")
    centred = a.get("_alone") and "y" not in a
    row = (f'style="{inserts.area_style(a)};align-items:center"' if centred else f'style="top:{a.get("y", 250)}px"')
    tx = cx.box("text", t0, t1, True)
    return (f'<div class="centerrow" {row}><div class="card-acc dk-hook" id="{gid}" {cx.box("card", t0, t1)}>'
            f'<span class="l l1" id="{gid}a" data-fitgroup="{gid}" data-fitmax="{a.get("max", 840)}" {tx}>{l1h}</span>'
            f'<span class="l l2" id="{gid}b" data-fitgroup="{gid}" data-fitmax="{a.get("max", 840)}" {tx}>{esc(l2)}</span>'
            f'<span class="dk-ul" id="{gid}u"></span></div></div>')


SPOKEN = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight",
          "9": "nine", "10": "ten"}


def _spoken(n):
    return SPOKEN.get(str(n), str(n))


# ---------------------------------------------------------------------------------------------- checklist
def checklist(cx, beat, a):
    cid, t0, t1 = cx.uid("chk"), beat["t0"], beat["t1"]
    a0 = beat.get("anchor_t0", t0)
    items, inst = a["items"], set(a.get("instant", []))
    ticks = a.get("ticks") or [None] * len(items)
    n, rh, head, foot, left, w = len(items), 104, 118, 78, 90, 900
    h = head + n * rh + foot
    top = inserts.place(a, h)
    blur_in(cx, beat, f"#{cid}", a0, y=60, scale=0.95, blur=5, dur=0.44, o0=0.9)
    first = min([at(cx, beat, ticks[i], 0.5 + 0.5 * i) for i in range(n) if i not in inst and i < len(ticks)
                 and ticks[i] is not False] or [a0])
    if first - a0 > 1.4:     # a long wait before the first tick: the camera reads the card's title first
        deck.focus(cx, beat, a0 + 0.5, 360, top + 60, 1.07, "title")
    rows, done = [], len(inst)
    for i, label in enumerate(items):
        rid = f"{cid}r{i}"
        blur_in(cx, beat, f"#{rid}", a0 + 0.12 + 0.07 * i, y=0, x=-40, scale=1, blur=8, dur=0.36)
        is_done = i in inst
        if not is_done and not (i < len(ticks) and ticks[i] is False):
            t = at(cx, beat, ticks[i] if i < len(ticks) else None, 0.5 + 0.5 * i)
            _tick(cx, beat, cid, rid, i, t, done, n, top + head + i * rh + rh / 2, label)
            done += 1
        rows.append(f'<div class="row{" done" if is_done else ""}" id="{rid}" style="top:{head + i * rh}px">'
                    f'<div class="dk-sw" id="{rid}w"></div><div class="ring"><div class="fill" id="{rid}f">{inserts.CHECK}</div>'
                    f'<div class="dk-burst" id="{rid}b"></div></div>'
                    f'<div class="lbl" id="{rid}l" {cx.box("text", t0, t1, True)}>{esc(label)}</div></div>')
    k0 = len(inst)
    digits = "".join(f"<i>{d}</i>" for d in range(n + 1))
    return (f'<div class="card chk dk-chk" id="{cid}" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px" '
            f'{cx.box("card", t0, t1)}><div class="ttl" {cx.box("text", t0, t1, True)}>{esc(a.get("title", ""))}</div>'
            f'<div class="dk-cnt"><span class="dk-odo"><span class="dk-col" id="{cid}c" style="transform:translateY({-k0 * 44}px)">'
            f'{digits}</span></span><span>/{n}</span></div>{"".join(rows)}'
            f'<div class="dk-bar"><div class="dk-fill" id="{cid}p" style="transform:scaleX({k0 / n:.4f})"></div></div></div>')


def _tick(cx, beat, cid, rid, i, t, done, n, y, label):
    ink = cx.brand["colors"]["ink"]
    cx.enter(beat, f"#{rid}f", t, {"opacity": 0, "scale": 0.3}, {"opacity": 1, "scale": 1}, dur=0.32, ease=E["pop"])
    ft(cx, f"#{rid}b", t, {"opacity": 0.9, "scale": 0.7}, {"opacity": 0, "scale": 2.2}, 0.5, E["snap"])
    ft(cx, f"#{rid}w", t, {"opacity": 1, "clipPath": "inset(0% 100% 0% 0% round 18px)"},
       {"opacity": 1, "clipPath": "inset(0% 0% 0% 0% round 18px)"}, 0.42, E["whip"])
    cx.to(f"#{rid}l", max(t, beat["t0"]), {"color": ink}, dur=0.2)
    ft(cx, f"#{cid}p", t, {"scaleX": done / n}, {"scaleX": (done + 1) / n}, 0.55, E["snap"])
    ft(cx, f"#{cid}c", t, {"y": -done * 44}, {"y": -(done + 1) * 44}, 0.42, E["snap"])
    deck.focus(cx, beat, t, 420, y, 1.12, f"tick {label}")
    cx.event(t, "tick", f"check {label}")
    accent(cx, t)


# ---------------------------------------------------------------------------------------------- table
def table(cx, beat, a):
    cols, rows = a.get("cols", ["TEST", "WHAT IT SHOWS"]), a["rows"]
    tid, t0, t1 = cx.uid("tbl"), beat["t0"], beat["t1"]
    a0 = beat.get("anchor_t0", t0)
    rh, w, left = 104, 920, 80
    height = 112 + len(rows) * rh + 18
    top = inserts.place(a, height)
    reveal = a.get("reveal") or [None] * len(rows)
    inst = a.get("instant", 0)
    blur_in(cx, beat, f"#{tid}", a0, y=60, scale=0.95, blur=5, dur=0.44, o0=0.9)
    parts, prev_y = [], None
    for i, (c1, c2) in enumerate(rows):
        rid = f"{tid}r{i}"
        spec = reveal[i] if i < len(reveal) else None
        t = at(cx, beat, spec, 0.3 + 0.35 * i) if i >= inst else a0
        ry = 100 + i * rh
        if i >= inst:
            blur_in(cx, beat, f"#{rid}", t, y=0, x=56, scale=1, blur=10, dur=0.38)
            ft(cx, f"#{rid}k", t, {"opacity": 1}, {"opacity": 0}, 0.16, E["exit"])
            sel_from = {"y": prev_y, "opacity": 1} if prev_y is not None else {"y": ry, "opacity": 0, "scaleX": 0.7}
            ft(cx, f"#{tid}s", t, sel_from, {"y": ry, "opacity": 1, "scaleX": 1}, 0.36, E["snap"])
            deck.focus(cx, beat, t, 420, top + ry + rh / 2, 1.1, f"row {c1}")
            cx.event(t, "pop", f"row {c1}")
            prev_y = ry
        tb = max(t, t0)
        if i >= inst:      # a loading skeleton holds the row's place until it lands (the card never reads empty)
            parts.append(f'<div class="dk-sk" id="{rid}k" style="top:{ry + 34}px"><i style="width:{150 + 37 * (i % 3)}px"></i>'
                         f'<i style="left:356px;width:{220 - 29 * (i % 2)}px"></i></div>')
        parts.append(f'<div class="row" id="{rid}" style="top:{ry}px;height:{rh}px">'
                     f'<span class="a" {cx.box("text", tb, t1, True)}>{esc(c1)}</span>'
                     f'<span class="b" {cx.box("text", tb, t1, True)}>{esc(c2)}</span></div>')
    head = "".join(f"<span>{esc(c)}</span>" for c in cols)
    return (f'<div class="card tbl dk-tbl" id="{tid}" style="left:{left}px;top:{top}px;width:{w}px;height:{height}px" '
            f'{cx.box("card", t0, t1)}><div class="hd" {cx.box("text", t0, t1, True)}>{head}</div><div class="hdline"></div>'
            f'<div class="dk-sel" id="{tid}s" style="height:{rh - 8}px;opacity:0"></div>{"".join(parts)}</div>')


# ---------------------------------------------------------------------------------------------- number
def number(cx, beat, a):
    uid, t0, t1 = cx.uid("num"), beat["t0"], beat["t1"]
    tx = cx.box("text", t0, t1, True)
    tn = at(cx, beat, a.get("n_at"), 0.0)
    tt = at(cx, beat, a.get("title_at"), 0.3)
    ft(cx, f"#{uid}n", tn, {"opacity": 0.25, "scale": 1.9, "filter": "blur(14px)"},
       {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, 0.26, E["stamp"])
    hide(cx, f"#{uid}t")
    room = max(0.3, min(0.66, (t1 - tt) * 0.6))       # the title is fully readable before the beat ends
    stg = min(0.026, room * 0.4 / max(1, len(str(a["title"]))))
    cx.tw.append(f"RRM.enter('letters',tl,'#{uid}t',{snap(tt)},{{stagger:{stg:.4f},dur:{room * 0.6:.3f}}});")
    cx.event(tt, "whoosh", f"number {a.get('n')} t")
    deck.punch(cx, beat, tt + 0.08, 1.05, f"number {a.get('n')}")
    deck.focus(cx, beat, tt, 540, 640, 1.07, f"title {a.get('title')}")
    accent(cx, tt)
    of = int(a.get("of") or 0)
    steps = ""
    if of > 1:
        n = int(re.sub(r"\D", "", str(a.get("n"))) or 1)
        blur_in(cx, beat, f"#{uid}st", beat.get("anchor_t0", t0) + 0.08, y=18, scale=1, blur=6, dur=0.36)
        segs = []
        for j in range(of):
            fill = ""
            if j < n - 1:
                fill = '<i style="transform:scaleX(1)"></i>'
            elif j == n - 1:
                fill = f'<i id="{uid}f" style="transform:scaleX(0)"></i>'
            segs.append(f"<b>{fill}</b>")
        ft(cx, f"#{uid}f", tt + 0.1, {"scaleX": 0}, {"scaleX": 1}, 0.5, E["snap"])
        steps = (f'<div class="dk-steps" id="{uid}st" {cx.box("card", t0, t1)}>{"".join(segs)}'
                 f'<span {tx}>{n} of {of}</span></div>')
    wrap = f"top:{a['y']}px" if "y" in a else f"{inserts.area_style(a)};justify-content:center"
    return (f'<div class="num numwrap dk-num" style="{wrap}"><div class="n" id="{uid}n" {tx}>{esc(a["n"])}</div>'
            f'<div class="t" id="{uid}t" data-fit="960,52" {tx}>{esc(a["title"])}</div>{steps}</div>')


# ---------------------------------------------------------------------------------------------- stat
def stat(cx, beat, a):
    sid, t0, t1 = cx.uid("st"), beat["t0"], beat["t1"]
    a0 = beat.get("anchor_t0", t0)
    tx = lambda t: cx.box("text", max(t, t0), t1, True)  # noqa: E731
    h = 70 + 280 + 150 + (100 if a.get("tag") else 0)
    top = inserts.place(a, h)
    vt = at(cx, beat, a.get("at"), 0.4)
    blur_in(cx, beat, f"#{sid}l", a0, y=20, scale=1, blur=8, dur=0.36, o0=0.4)
    pre = ""
    if a.get("pre"):
        pt = at(cx, beat, a.get("pre_at"), 0.0)
        cx.enter(beat, f"#{sid}p", pt, {"opacity": 0, "x": -90, "filter": "blur(16px)"},
                 {"opacity": 1, "x": 0, "filter": "blur(0px)"}, dur=0.2, ease=E["snap"])
        pre = f'<span class="pre" id="{sid}p" {tx(pt)}>{esc(a["pre"])}</span>'
    val = str(a["value"])
    if val.isdigit() and int(val) <= 30:
        k = int(val)
        col = "".join(f"<i>{d}</i>" for d in range(k + 1))
        hide(cx, f"#{sid}o")
        cx.set(f"#{sid}o", max(t0, vt - 0.4), {"autoAlpha": 1})
        ft(cx, f"#{sid}c", vt - 0.4, {"y": 0}, {"y": -k * 250}, 0.52, E["snap"])
        num = f'<span class="dk-vodo" id="{sid}o"><span class="dk-vcol" id="{sid}c">{col}</span></span>'
    else:
        num = f'<span class="v dk-v" id="{sid}o" style="position:absolute;left:0;top:0">{esc(val)}</span>'
        cx.enter(beat, f"#{sid}o", vt, {"opacity": 0, "scale": 1.6, "filter": "blur(12px)"},
                 {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, dur=0.24, ease=E["stamp"])
    ft(cx, f"#{sid}vb", vt + 0.1, {"scale": 1.1}, {"scale": 1}, 0.4, E["wobble"])
    cx.event(vt, "thud", f"stat {a.get('value')}")
    deck.focus(cx, beat, vt, 540, top + 70 + 140, 1.1, f"value {val}")
    deck.punch(cx, beat, vt + 0.1, 1.05, "value")
    accent(cx, vt)
    meter, tag = _meter(cx, beat, a, sid, top + 70 + 280 + 30, vt), ""
    if a.get("tag"):
        tt = at(cx, beat, a["tag"].get("at"), 1.0)
        blur_in(cx, beat, f"#{sid}g", tt, y=24, scale=0.86, blur=8, dur=0.34, ease=E["pop"])
        ft(cx, f"#{sid}k", tt, {"x": a.get("_mark_x", 380)}, {"x": a.get("_mark_x", 380) + 120}, 0.5, E["snap"])
        cx.event(tt, "pop", "stat tag")
        deck.focus(cx, beat, tt, 540, top + 70 + 280 + 80, 1.06, "tag")
        tag = (f'<div class="centerrow" style="top:{top + 70 + 280 + 150}px"><div class="tag stat-tag" id="{sid}g" '
               f'style="position:relative" {tx(tt)}>{esc(a["tag"]["text"])}</div></div>')
    return (f'<div class="statwrap dk-stat" style="top:{top}px">'
            f'<div class="lbl" id="{sid}l" {cx.box("text", t0, t1, True)}>{esc(a.get("label", ""))}</div>'
            f'<div class="row">{pre}<span class="vbox" id="{sid}vb"><span class="v ghost">{esc(val)}</span>'
            f'<span class="v dk-sizer" {tx(vt)}>{esc(val)}</span>{num}</span>'
            f'</div></div>{meter}{tag}')


def _meter(cx, beat, a, sid, y, vt):
    """Zone meter under the value: below the line (gold) | over it (alert); the marker slides to the line."""
    mt = at(cx, beat, a.get("pre_at"), 0.1)
    w, x0, mark = 780, 150, 0.5
    a["_mark_x"] = round(w * mark - 23)
    ft(cx, f"#{sid}m", mt, {"clipPath": "inset(0% 100% 0% 0% round 999px)"},
       {"clipPath": "inset(0% 0% 0% 0% round 999px)"}, 0.5, E["whip"])
    hide(cx, f"#{sid}k")
    cx.set(f"#{sid}k", vt - 0.3, {"autoAlpha": 1})
    ft(cx, f"#{sid}k", vt - 0.3, {"x": -23}, {"x": a["_mark_x"]}, 0.55, E["snap"])
    return (f'<div class="dk-meter" style="left:{x0}px;top:{y}px;width:{w}px" {cx.box("card", beat["t0"], beat["t1"])}>'
            f'<div class="dk-mtrack" id="{sid}m"><i style="width:{mark * 100:.0f}%"></i><b></b></div>'
            f'<div class="dk-mline" style="left:{w * mark - 3:.0f}px"></div><div class="dk-mk" id="{sid}k"></div></div>')


# ---------------------------------------------------------------------------------------------- full-frame overlays
def name_card(cx, beat, a):
    nid, t0, t1 = cx.uid("nc"), beat["t0"], beat["t1"]
    h = 230 if a.get("kicker") else 180
    top = overlay.band(a, h, a.get("align", "center"))
    t = at(cx, beat, a.get("at"), 0.0)
    blur_in(cx, beat, f"#{nid}", t, y=34, scale=0.92, blur=12, dur=0.42, o0=0.3)
    ft(cx, f"#{nid}bar", t + 0.08, {"scaleY": 0}, {"scaleY": 1}, 0.45, E["whip"])
    role = ""
    if a.get("role"):
        rt = at(cx, beat, a.get("role_at"), 0.25)
        cx.enter(beat, f"#{nid}r", rt, {"opacity": 0, "x": -110, "filter": "blur(18px)"},
                 {"opacity": 1, "x": 0, "filter": "blur(0px)"}, dur=0.2, ease=E["snap"])
        ft(cx, f"#{nid}ru", rt + 0.1, {"scaleX": 0}, {"scaleX": 1}, 0.4, E["whip"])
        cx.event(rt, "click", "name card role")
        role = (f'<div class="ncr" id="{nid}r" {cx.box("text", max(rt, t0), t1, True)}>{esc(a["role"])}'
                f'<span class="dk-ru" id="{nid}ru"></span></div>')
    kick = f'<div class="nck" {cx.box("text", t0, t1, True)}>{esc(a["kicker"])}</div>' if a.get("kicker") else ""
    return (f'<div class="centerrow" style="top:{top}px"><div class="namecard dk-nc" id="{nid}" {cx.box("card", t0, t1)}>'
            f'<div class="ncbar" id="{nid}bar"></div><div>{kick}<div class="ncn" data-fit="820,40" {cx.box("text", t0, t1, True)}>'
            f'{esc(a.get("name") or cx.brand.get("name", ""))}</div>{role}</div></div></div>')


SEARCH = ('<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2.6" '
          'stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/></svg>')
ARROW = ('<svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/></svg>')


def prompt(cx, beat, a):
    """Search / prompt bar that types on the words. args: text, placeholder, focus_at, type_at, type_end, done_at, done."""
    pid, t0, t1 = cx.uid("pb"), beat["t0"], beat["t1"]
    h = 132 + 30 + 92
    top = overlay.band(a, h, a.get("align", "center")) if beat["layout"] != "split" else inserts.place(a, h)
    t_in = at(cx, beat, a.get("at"), 0.0)
    blur_in(cx, beat, f"#{pid}", t_in, y=50, scale=0.9, blur=14, dur=0.44, o0=0.0)
    cx.event(t_in, "whoosh", "prompt bar")
    tf = at(cx, beat, a.get("focus_at"), 0.4)
    ft(cx, f"#{pid}ring", tf, {"opacity": 0, "scale": 1.06}, {"opacity": 1, "scale": 1}, 0.3, E["snap"])
    text = a["text"]
    ts = at(cx, beat, a.get("type_at"), 0.8)
    te = at(cx, beat, a.get("type_end"), ts + 0.05 * len(text)) if a.get("type_end") else ts + 0.055 * len(text)
    step = max(1 / 30, (te - ts) / max(1, len(text)))
    cx.set(f"#{pid}ph", ts, {"autoAlpha": 0})
    chars = []
    for i, ch in enumerate(text):
        cx.set(f"#{pid}c{i}", ts + i * step, {"display": "inline"})
        chars.append(f'<span class="tc" id="{pid}c{i}">{esc(ch) if ch != " " else "&nbsp;"}</span>')
    cx.init.append(f"document.querySelectorAll('#{pid} .tc').forEach(function(e){{e.style.display='none';}});")
    blink = [x / 2 for x in range(int((t1 - t0) * 2))]
    for j, bt in enumerate(blink):     # caret blinks while idle, solid while typing
        tt = t0 + bt
        if ts - 0.05 <= tt <= te + 0.4:
            continue
        cx.set(f"#{pid}k", tt, {"opacity": 1 if j % 2 == 0 else 0})
    cx.set(f"#{pid}k", ts, {"opacity": 1})
    cx.event(ts, "type", "prompt types")
    td = at(cx, beat, a.get("done_at"), te - ts + 0.3)
    td = max(td, te + 0.08)
    ft(cx, f"#{pid}go", td, {"scale": 0.7}, {"scale": 1}, 0.32, E["pop"])
    blur_in(cx, beat, f"#{pid}d", td + 0.06, y=-26, scale=0.9, blur=10, dur=0.38, ease=E["land"])
    cx.enter(beat, f"#{pid}dt", td + 0.12, {"opacity": 0, "scale": 0.3}, {"opacity": 1, "scale": 1}, dur=0.3, ease=E["pop"])
    cx.event(td + 0.06, "pop", "prompt done chip")
    accent(cx, td)
    done = a.get("done", "Added")
    return (f'<div class="dk-pb" id="{pid}" style="top:{top}px" {cx.box("card", t0, t1)}>'
            f'<div class="dk-ring" id="{pid}ring"></div><div class="dk-si">{SEARCH}</div>'
            f'<div class="dk-tx"><span class="dk-ph" id="{pid}ph">{esc(a.get("placeholder", "Search"))}</span>'
            f'<span {cx.box("text", max(ts, t0), t1, True)}>{"".join(chars)}</span><span class="dk-k" id="{pid}k"></span></div>'
            f'<div class="dk-go" id="{pid}go">{ARROW}</div></div>'
            f'<div class="centerrow" style="top:{top + 162}px"><div class="chipx accent dk-done" id="{pid}d" '
            f'{cx.box("text", max(td, t0), t1, True)}><span class="cht" id="{pid}dt">{overlay.TICK}</span>{esc(done)}</div></div>')


INSERTS = {"hook_card": hook_card, "checklist": checklist, "table": table, "number": number, "stat": stat,
           "name_card": name_card, "prompt": prompt}


def css(brand):
    from theme import rgba
    c = brand["colors"]
    return f"""
/* split-deck motion v2 phase 3 (deck_inserts.py) */
.dk-hook{{position:relative;padding:44px 52px 50px}}
.dk-hook .l{{font-size:116px}}
.dk-hook .hkn{{display:inline-block;font-weight:900;color:var(--accent2);transform-origin:50% 60%}}
.dk-ul{{position:absolute;left:52px;right:52px;bottom:26px;height:10px;border-radius:6px;background:var(--accent2);transform-origin:0 50%;
  transform:scaleX(0)}}
.dk-chk .ttl{{left:44px;top:40px;font-size:44px}}
.dk-chk .row{{left:24px;right:24px;height:104px;padding-left:20px;border-radius:18px}}
.dk-chk .lbl{{font-size:48px;position:relative}}
.dk-chk .ring{{width:62px;height:62px;position:relative}}
.dk-chk .fill svg{{width:34px;height:34px}}
.dk-sw{{position:absolute;left:0;top:6px;right:0;bottom:6px;border-radius:18px;background:{rgba(c['accent2'], .22)};opacity:0}}
.dk-burst{{position:absolute;left:-10px;top:-10px;width:74px;height:74px;border-radius:50%;border:4px solid var(--accent);opacity:0}}
.dk-cnt{{position:absolute;right:44px;top:36px;display:flex;align-items:flex-start;font:900 40px/44px var(--fd);color:var(--accent);
  letter-spacing:-.02em}}
.dk-odo{{display:inline-block;height:44px;overflow:hidden}}
.dk-col{{display:flex;flex-direction:column}}
.dk-col i,.dk-vcol i{{font-style:normal;display:block}}
.dk-bar{{position:absolute;left:44px;right:44px;bottom:30px;height:14px;border-radius:999px;background:{rgba(c['ink'], .08)};overflow:hidden}}
.dk-fill{{position:absolute;inset:0;border-radius:999px;background:var(--accent);transform-origin:0 50%}}
.dk-tbl .row{{left:20px;right:20px;border-bottom:none}}
.dk-tbl .row .a{{font-size:46px;width:360px}}
.dk-tbl .row .b{{font-size:40px}}
.dk-sk{{position:absolute;left:44px;right:44px;height:34px}}
.dk-sk i{{position:absolute;left:0;top:0;display:block;height:30px;border-radius:10px;background:{rgba(c['ink'], .07)}}}
.dk-sel{{position:absolute;left:20px;right:20px;top:4px;border-radius:18px;background:{rgba(c['accent2'], .24)};
  box-shadow:inset 6px 0 0 var(--accent);transform-origin:0 50%}}
.dk-num .t{{font-size:118px}}
.dk-steps{{display:flex;align-items:center;gap:14px;margin-top:40px}}
.dk-steps b{{position:relative;display:block;width:124px;height:20px;border-radius:999px;background:{rgba(c['ink'], .1)};overflow:hidden}}
.dk-steps b i{{position:absolute;inset:0;background:var(--accent);transform-origin:0 50%;border-radius:999px}}
.dk-steps span{{font:800 36px/1 var(--fb);letter-spacing:.06em;color:var(--soft);margin-left:16px;white-space:nowrap}}
.dk-stat .lbl{{font-size:56px;height:62px}}
.dk-stat .row{{height:280px}}
.dk-stat .vbox{{transform-origin:50% 70%}}
.dk-sizer{{visibility:hidden}}
.dk-vodo{{position:absolute;left:0;top:0;height:250px;overflow:hidden;display:inline-block}}
.dk-vcol{{display:flex;flex-direction:column;font:900 330px/250px var(--fd);letter-spacing:-.05em;color:var(--accent)}}
.dk-meter{{position:absolute;height:60px}}
.dk-mtrack{{position:absolute;left:0;right:0;top:16px;height:28px;border-radius:999px;overflow:hidden;display:flex}}
.dk-mtrack i{{display:block;height:100%;background:var(--accent2)}}
.dk-mtrack b{{display:block;flex:1;height:100%;background:var(--alert)}}
.dk-mline{{position:absolute;top:0;width:6px;height:60px;border-radius:3px;background:var(--ink)}}
.dk-mk{{position:absolute;left:0;top:7px;width:46px;height:46px;border-radius:50%;background:#fff;border:6px solid var(--ink);
  box-shadow:0 6px 16px {rgba(c['ink'], .3)}}}
.dk-nc .ncn{{font-size:84px}}
.dk-nc .ncr{{position:relative;display:inline-block;font-size:54px}}
.dk-nc .ncbar{{transform-origin:50% 0}}
.dk-ru{{position:absolute;left:0;right:0;bottom:-8px;height:7px;border-radius:4px;background:var(--accent2);transform-origin:0 50%;
  transform:scaleX(0)}}
.dk-pb{{position:absolute;left:90px;width:900px;height:132px;border-radius:999px;background:#fff;display:flex;align-items:center;
  gap:22px;padding:0 22px 0 38px;box-shadow:0 26px 60px rgba(0,0,0,.24),0 4px 14px rgba(0,0,0,.1)}}
.dk-ring{{position:absolute;inset:-7px;border-radius:999px;border:5px solid var(--accent);opacity:0}}
.dk-si{{color:var(--soft);display:flex}}
.dk-tx{{flex:1;display:flex;align-items:center;font:700 54px/1 var(--fd);letter-spacing:-.015em;color:var(--ink);white-space:nowrap;
  position:relative;height:70px}}
.dk-ph{{position:absolute;left:0;color:var(--faint);font-weight:600}}
.dk-k{{display:inline-block;width:5px;height:58px;margin-left:4px;background:var(--accent);border-radius:3px}}
.dk-go{{width:88px;height:88px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}}
.dk-done{{height:92px;font-size:46px}}
"""
