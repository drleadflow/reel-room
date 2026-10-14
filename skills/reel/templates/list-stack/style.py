"""LIST STACK style: one take of the speaker, full frame; a title and a numbered list above the head that fill in,
item by item, exactly as each item is spoken. Captions in a clean pill at chest height.

List rules (2026-10-10), kept by the Motion v2 phase 3 kinetic list:
  1. Fixed scaffold: every number glyph keeps one position and size for the whole video. Rows never move between
     slots: every row motion (stamp, push, compress) is centred on its own number badge, so the glyph stays put.
  2. The ACTIVE item (the one being spoken) is in the emphasis colour; earlier items drop to a calm state.
  3. Rows are spaced evenly from the rendered text height and kept compact inside the band above the head.
  4. The list clears before the next topic (`hide` windows, `clear_at`), it is not held for its own sake.
  5. Rows are revealed as spoken by default (faint empty slots read as noise at phone size; `empty: "slots"` keeps them).

Kinetic layer (motion v2 phase 3): the masthead number stamps in and pulses on the spoken count, the title lines push
up through a mask, a progress tick per item fills under the title, each row's number stamps in on its cut, the accent
fill wipes across the row from the badge with a light sheen sweep and a subtle push, the item text rises through a
mask on its spoken word, details blur in on their words, the tag pops and replaces them, and a finished row compresses
and dims in place (its number never moves). The camera settle/punch comes from the engine motion layer.

Loaded by templates/split/compose.py when project.json has "style": "list-stack". The list plan goes to
`cx.list_plan` (compose stores it in layout_boxes.json "list"; gallery.py writes <out>/list.json for QA).
"""
import json
import os
import sys

from ctx import esc, snap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hero as HERO  # noqa: E402

DEFAULTS = {
    "captions": {"mode": "pill", "full_style": "pill", "max_words": 3, "max_chars": 24},
    "head_margin": 22,
}

ROW_X, ROW_W = 100, 880
DONE_K = 0.84          # a finished row's card compresses to this height (centred on its badge)
PUSH_K = 1.025         # the active row's push (scaled about its badge centre)
SEG_W, SEG_GAP = 54, 8  # progress ticks under the title


def _js(cx, line):
    cx.tw.append(line)


def _ft(cx, sel, t, frm, to, dur, ease, stagger=None):
    """fromTo that never shows its from-state before its frame (immediateRender false), ease by motion token."""
    v = dict(to, duration=dur, ease=ease, immediateRender=False)
    if stagger:
        v["stagger"] = stagger
    _js(cx, f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(v)},{snap(t)});")


def _rrm(cx, name, sel, t, **opts):
    """An engine entrance (motion.js RRM.enter) on one element, at a frame-snapped time."""
    _js(cx, f"RRM.enter({json.dumps(name)},tl,document.querySelector({json.dumps(sel)}),{snap(t)},{json.dumps(opts)});")


def _push(cx, sel, t_hide, t, dur):
    """Mask push that is already hidden from t_hide (no flash of the settled line before its push starts)."""
    _js(cx, f"(function(){{var e=document.querySelector({json.dumps(sel)});tl.set(RRM.mask(e),{{yPercent:110}},{snap(t_hide)});"
            f"RRM.enter('maskPush',tl,e,{snap(t)},{{dur:{dur}}});}})();")


def _masthead(cx, b, a, lid, top, h, n):
    t = a.get("title", {})
    t0, t1 = b["t0"], b["t1"]
    tx = lambda: cx.box("text", t0, t1, True)  # noqa: E731
    num = esc(t.get("n", str(n)))
    l1 = esc(t.get("l1", "THINGS"))
    l2 = esc(t.get("l2", ""))
    sub = f'<div class="lsl2" id="{lid}t2" {tx()}>{l2}</div>' if l2 else ""
    segs = "".join(f'<i><b id="{lid}g{i}"></b></i>' for i in range(n))
    return (f'<div class="lsm" style="top:{top}px;height:{h}px"><div class="lsn" id="{lid}n" {cx.box("glyph", t0, t1, True)}>{num}</div>'
            f'<div class="lst"><div class="lsl1" id="{lid}t1" data-fit="660,40" {tx()}>{l1}</div>{sub}'
            f'<div class="lspg" id="{lid}pg">{segs}</div></div></div>')


def _mast_in(cx, b, lid, t, has_l2, first=False):
    """Masthead entrance: the number stamps (frame 0 already carries a faint one), the lines push up through masks."""
    o0 = 0.4 if first and t < 0.05 else 0
    cx.enter(b, f"#{lid}n", t, {"opacity": o0, "scale": 1.7, "filter": "blur(14px)"},
             {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, dur=0.26, ease="power4.out")
    _push(cx, f"#{lid}t1", t, t, 0.36)
    if has_l2:
        _push(cx, f"#{lid}t2", t, t + 0.1, 0.34)
    cx.event(t, "pop", "list title number")
    cx.event(t + 0.24, "click", "list title lines")


def _count(cx, lid, t, n):
    """On the spoken count ('five'): the big number pulses and the empty progress ticks pop in one by one."""
    _ft(cx, f"#{lid}n", t, {"scale": 1.32, "filter": "blur(6px)"}, {"scale": 1, "filter": "blur(0px)"}, 0.3, "power4.out")
    _ft(cx, f"#{lid}pg i", t + 0.06, {"opacity": 0, "scale": 0.3}, {"opacity": 1, "scale": 1}, 0.3, "back.out(2.2)",
        stagger=0.05)
    cx.event(t, "pop", "count pulse")
    cx.event(t + 0.06 + 0.05 * (n - 1), "tick", "progress ticks")


def _row_on(cx, b, lid, rid, i, ton):
    """Row i becomes ACTIVE on its cut: number stamps, accent fill wipes from the badge, sheen sweeps, row pushes."""
    cx.set(f"#{rid}", ton, {"autoAlpha": 1})
    _js(cx, f'tl.set("#{rid}",{{attr:{{class:"lsr active"}}}},{snap(ton)});')
    cx.enter(b, f"#{rid}b", ton, {"opacity": 0, "scale": 1.6, "filter": "blur(10px)"},
             {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, dur=0.22, ease="power4.out")
    cx.enter(b, f"#{rid}c", ton, {"opacity": 0, "scaleX": 0.86, "scaleY": 0.7}, {"opacity": 1, "scaleX": 1, "scaleY": 1},
             dur=0.34, ease="expo.out")
    _ft(cx, f"#{rid}f", ton + 0.04, {"clipPath": "inset(0% 100% 0% 0% round 22px)"},
        {"clipPath": "inset(0% 0% 0% 0% round 22px)"}, 0.42, "expo.inOut")
    _ft(cx, f"#{rid}s", ton + 0.3, {"xPercent": -120, "autoAlpha": 1}, {"xPercent": 620}, 0.7, "power2.inOut")
    cx.set(f"#{rid}s", ton + 1.0, {"autoAlpha": 0})
    _ft(cx, f"#{rid}", ton + 0.08, {"scale": 1}, {"scale": PUSH_K}, 0.5, "power2.inOut")
    _ft(cx, f"#{lid}g{i}", ton + 0.12, {"scaleX": 0}, {"scaleX": 1}, 0.36, "expo.out")
    cx.event(ton, "pop", f"slot {i + 1} number")
    cx.event(ton + 0.12, "tick", f"progress {i + 1}")
    cx.event(ton + 0.3, "whoosh", f"slot {i + 1} highlight sweep")


def _row_done(cx, rid, lid, i, td, ink):
    """Row i finishes: fill clears, the card compresses about its badge, text dims, the push releases."""
    _js(cx, f'tl.set("#{rid}",{{attr:{{class:"lsr done"}}}},{snap(td)});')
    cx.to(f"#{rid}f", td, {"opacity": 0}, dur=0.2, ease="power2.out")
    cx.to(f"#{rid}c", td, {"scaleY": DONE_K, "opacity": 0.86}, dur=0.42, ease="expo.out")
    cx.to(f"#{rid}", td, {"scale": 1}, dur=0.42, ease="expo.out")
    cx.to(f"#{rid}y", td, {"scale": 0.93, "color": ink}, dur=0.2, ease="power2.out")
    cx.to(f"#{lid}g{i}", td, {"backgroundColor": ink}, dur=0.3, ease="power2.out")
    cx.event(td + 0.1, "tick", f"slot {i + 1} done")


def _row_text(cx, b, rid, i, it, ton, t0, t1):
    """Label (mask push on its word), details (blur in on their words), tag (pops and takes the details' place)."""
    parts = []
    if it.get("label"):
        tl_ = cx.cue(it.get("at"), b, lead="type", fallback=0.4) if it.get("at") else cx.when(None, b, 0.4)
        tl_ = max(tl_, (ton if ton is not None else t0) + 0.2)
        _rrm(cx, "maskPush", f"#{rid}l", tl_, dur=0.34)
        cx.to(f"#{rid}p", tl_, {"opacity": 0, "scaleX": 0.4}, dur=0.16, ease="power3.in")
        cx.event(tl_, "click", f"item {i + 1} {it['label']}")
        parts.append(f'<span class="lslab" id="{rid}l" {cx.box("text", max(tl_, t0), t1, True)}>{esc(it["label"])}</span>')
    det = it.get("detail") or []
    if det:
        spans = []
        for k, p in enumerate(det):
            tp = cx.cue(p.get("at"), b, lead="visual", fallback=1.0) if p.get("at") else cx.when(None, b, 1.0)
            cx.enter(b, f"#{rid}d{k}", tp, {"opacity": 0, "x": -18, "filter": "blur(8px)"},
                     {"opacity": 1, "x": 0, "filter": "blur(0px)"}, dur=0.3, ease="expo.out")
            cx.event(tp, "tick", f"detail {p['text']}")
            spans.append(f'<span id="{rid}d{k}" {cx.box("text", max(tp, t0), t1, True)}>{esc(p["text"])}</span>')
        parts.append(f'<span class="lsdet" id="{rid}dw">{" ".join(spans)}</span>')
    tag = it.get("tag")
    if tag:
        tt = cx.cue(tag.get("at"), b, lead="stamp", fallback=2.0) if tag.get("at") else cx.when(None, b, 2.0)
        if det:   # the details leave fast (exit ~2x faster than the entrance), the tag takes their place
            cx.to(f"#{rid}dw", tt - 0.12, {"opacity": 0, "x": 24, "filter": "blur(8px)"}, dur=0.14, ease="power3.in")
        cx.enter(b, f"#{rid}t", tt, {"opacity": 0, "scale": 0.5, "x": 30, "filter": "blur(6px)"},
                 {"opacity": 1, "scale": 1, "x": 0, "filter": "blur(0px)"}, dur=0.34, ease="back.out(2.2)")
        cx.event(tt, "pop", f"tag {tag['text']}")
        parts.append(f'<span class="lstag" id="{rid}t" {cx.box("text", max(tt, t0), t1, True)}>{esc(tag["text"])}</span>')
    return parts


LIST_MOVES = ["zoom", "iris"]   # a new item zooms through or opens on a circle (the list and hero stay still above)


def _moves(cx):
    """Narrow the engine's transition moves to LIST_MOVES unless project.json motion.transitions names its own."""
    m = getattr(cx, "motion_cfg", None)
    if m is None:
        return
    try:
        pj = json.load(open(os.path.join(cx.dir, "project.json")))
    except (OSError, ValueError):
        pj = {}
    tr = (pj.get("motion") or {}).get("transitions") if isinstance(pj.get("motion"), dict) else None
    if not (isinstance(tr, dict) and tr.get("moves")):
        m["moves"] = list(LIST_MOVES)


def _fit_rows(a, rows_top, y1, n):
    fs = int(a.get("label_px", 46))
    row_h, gap = round(fs * 1.44), max(6, round(fs * 0.18))   # even rhythm from the text height
    while rows_top + n * row_h + (n - 1) * gap > y1 and fs > 30:
        fs -= 2
        row_h, gap = round(fs * 1.44), max(6, round(fs * 0.18))
    return fs, row_h, gap


def list_stack(cx, b, a):
    """args: title{n,l1,l2,at}, n, items[{on, label, at, detail:[{text, at}], tag:{text, at}}], hide[{from, until}],
    clear_at, empty ("hidden"|"slots"), transitions (default true: cuts where an item lands or the list leaves/returns
    count as section changes for the motion layer). `on` = when the row appears and becomes active ('#cut' lands on the cut).
    title.at = the spoken count ("@five"): the number pulses and the progress ticks pop in."""
    lid, t0, t1 = cx.uid("ls"), b["t0"], b["t1"]
    y0, y1 = a.get("_area", (220, 726))
    n = int(a.get("n", 5))
    ink = cx.brand["colors"].get("ink", "#1D1214")
    items = (a.get("items", []) + [{}] * n)[:n]
    mast_top, mast_h = y0 + 10, int(a.get("title_h", 124))
    rows_top = mast_top + mast_h + 14
    fs, row_h, gap = _fit_rows(a, rows_top, y1, n)
    if rows_top + n * row_h + (n - 1) * gap > y1:
        cx.warn(f"list-stack: {n} rows do not fit above the head (band {y0}-{y1})")
    ys = [rows_top + i * (row_h + gap) for i in range(n)]
    badge = row_h - 16
    bcx, bcy = 10 + badge / 2, row_h / 2          # badge centre inside the row: every row move is centred here
    show_empty = a.get("empty", "hidden") == "slots"
    title = a.get("title", {})
    html = ['<div class="lsL" id="' + lid + 'L">', _masthead(cx, b, a, lid, mast_top, mast_h, n)]
    _mast_in(cx, b, lid, t0, bool(title.get("l2")), first=True)
    if title.get("at"):
        _count(cx, lid, cx.cue(title["at"], b, lead="stamp"), n)
    on_times, plan, heroes = [], [], []
    cx.cut_motion = dict(getattr(cx, "cut_motion", None) or {})
    for i, it in enumerate(items):
        rid = f"{lid}r{i}"
        ton = cx.when(it["on"], b, 0.0) if it.get("on") is not None else None
        on = str(it.get("on", ""))
        if on.startswith("#") and it.get("punch", True):     # a punch-in on the spoken number, on the item's cut
            cx.cut_motion[on[1:].split("+")[0]] = {"punch": it.get("punch") if isinstance(it.get("punch"), str) else f"@{i + 1}"}
        if ton is not None and it.get("hero"):               # the item's big moment first, then it lands in the list
            geo = {"y0": y0, "y1": y1, "badge_c": (ROW_X + 10 + badge / 2, ys[i] + row_h / 2), "badge_px": badge * 0.5}
            hh, ton = HERO.build(cx, b, lid, i, it, geo)
            heroes.append(hh)
        on_times.append(ton)
        if not show_empty:
            cx.init.append(f'gsap.set("#{rid}",{{autoAlpha:0}});')
        if ton is not None:
            _row_on(cx, b, lid, rid, i, ton)
            plan.append({"n": i + 1, "t_in": round(ton, 3),
                         "box": [ROW_X + 10, ys[i] + (row_h - badge) // 2, badge, badge],
                         "row": [ROW_X, ys[i], ROW_W, row_h]})
        parts = _row_text(cx, b, rid, i, it, ton, t0, t1)
        html.append(
            f'<div class="lsr" id="{rid}" style="left:{ROW_X}px;top:{ys[i]}px;width:{ROW_W}px;height:{row_h}px;'
            f'--fs:{fs}px;--bd:{badge}px;transform-origin:{bcx:.1f}px {bcy:.1f}px" {cx.box("card", t0, t1)}>'
            f'<div class="lsc" id="{rid}c" style="transform-origin:{bcx:.1f}px {bcy:.1f}px"><div class="lsf" id="{rid}f"></div>'
            f'<div class="lssh" id="{rid}s"></div></div>'
            f'<div class="lsb" id="{rid}b"><span>{i + 1}</span></div><div class="lsph" id="{rid}p"></div>'
            f'<div class="lsbody" id="{rid}y">{"".join(parts)}</div></div>')
    # a new item landing on a cut, and the list leaving / returning on a cut, open a new section: the engine motion
    # layer may give those cuts a transition (level budget; captions and this list stay outside the transition)
    secs = {str(x)[1:].split("+")[0].split("-")[0] for x in [it.get("on") for it in items] +
            [h.get(k) for h in a.get("hide", []) for k in ("from", "until")] if isinstance(x, str) and x.startswith("#")}
    if a.get("transitions", True):
        cx.section_cuts = set(getattr(cx, "section_cuts", None) or ()) | secs
        _moves(cx)
    act = sorted((t, i) for i, t in enumerate(on_times) if t is not None)
    for (_ta, ia), (tb, _ib) in zip(act, act[1:]):
        _row_done(cx, f"{lid}r{ia}", lid, ia, tb, ink)
    hidden = []
    for h in a.get("hide", []):
        hf = cx.when(h["from"], b, 0.0)
        hu = cx.when(h["until"], b, 0.0) if h.get("until") is not None else t1
        cx.set(f"#{lid}", hf, {"autoAlpha": 0})
        if hu < t1 - 1e-3:
            cx.set(f"#{lid}", hu, {"autoAlpha": 1})
            _mast_in(cx, b, lid, hu, bool(title.get("l2")))     # the list comes back: a fresh title entrance
        hidden.append([round(hf, 3), round(hu, 3)])
    clear = cx.when(a["clear_at"], b, t1) if a.get("clear_at") is not None else t1
    if clear < t1 - 0.05:
        for k, (_t, i) in enumerate(sorted(act, reverse=True)):
            cx.to(f"#{lid}r{i}", clear + 0.04 * k, {"opacity": 0, "y": -16, "filter": "blur(8px)"}, dur=0.18, ease="power3.in")
        cx.to(f"#{lid}", clear + 0.2, {"autoAlpha": 0}, dur=0.16, ease="power3.in")
        cx.event(clear, "whoosh", "list clears")
    # "scaffold" (QA: every number is on screen from the first reveal) only holds when the empty slots show
    cx.list_plan = {"items": plan, "clear_at": round(clear, 3) if clear < t1 - 0.05 else None, "scaffold": show_empty, "hidden": hidden,
                    "row": {"x": ROW_X, "w": ROW_W, "h": row_h, "gap": gap, "tops": ys, "label_px": fs, "badge": badge},
                    "band": [y0, y1]}
    return f'<div class="lsw" id="{lid}">{"".join(html)}</div>{"".join(heroes)}</div>'


INSERTS = {"list_stack": list_stack}


def css(brand, cx):
    c = brand["colors"]
    return HERO.css() + f"""
.lsw{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.lsm{{position:absolute;left:0;width:1080px;display:flex;align-items:center;justify-content:center;gap:24px}}
.lsn{{font:900 186px/.74 var(--fd);height:124px;display:flex;align-items:center;letter-spacing:-.06em;color:var(--accent);
  text-shadow:0 2px 0 rgba(255,255,255,.4),0 12px 34px rgba(122,30,46,.22)}}
.lst{{display:flex;flex-direction:column;gap:8px}}
.lsl1{{font:900 64px/1 var(--fd);letter-spacing:-.03em;word-spacing:.06em;text-transform:uppercase;color:var(--ink);white-space:nowrap}}
.lsl2{{font:700 32px/1 var(--fb);color:var(--accent);white-space:nowrap;letter-spacing:-.01em}}
.lspg{{display:flex;gap:{SEG_GAP}px;margin-top:4px;height:9px}}
.lspg i{{display:block;width:{SEG_W}px;height:9px;border-radius:5px;background:rgba(29,18,20,.14);overflow:hidden;opacity:0}}
.lspg b{{display:block;width:100%;height:100%;border-radius:4px;background:var(--accent);transform:scaleX(0);transform-origin:0 50%}}
/* row: the badge glyph never leaves its slot; every move (stamp, push, compress) is centred on the badge */
.lsr{{position:absolute}}
.lsc{{position:absolute;inset:0;border-radius:22px;overflow:hidden;background:rgba(255,255,255,.62);
  box-shadow:0 8px 22px rgba(29,18,20,.08);outline:2px solid rgba(255,255,255,.8);outline-offset:-2px}}
.lsf{{position:absolute;inset:0;background:var(--accent);clip-path:inset(0% 100% 0% 0% round 22px)}}
.lssh{{position:absolute;top:-20%;bottom:-20%;left:0;width:140px;opacity:0;visibility:hidden;transform:skewX(-18deg);
  background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.34),rgba(255,255,255,0))}}
.lsb{{position:absolute;left:10px;top:8px;width:var(--bd);height:var(--bd);border-radius:50%;border:2.5px solid rgba(29,18,20,.28);
  box-sizing:border-box;display:flex;align-items:center;justify-content:center;font:800 calc(var(--bd) * .5)/1 var(--fd);color:rgba(29,18,20,.5)}}
.lsph{{position:absolute;left:calc(var(--bd) + 30px);top:50%;margin-top:-6px;width:240px;height:12px;border-radius:6px;
  background:rgba(29,18,20,.12);transform-origin:0 50%}}
.lsbody{{position:absolute;left:calc(var(--bd) + 30px);right:20px;top:0;bottom:0;display:flex;align-items:center;gap:18px;
  white-space:nowrap;transform-origin:0 50%;color:#F6F2EE}}
.lslab{{font:800 var(--fs)/1 var(--fd);letter-spacing:-.025em;word-spacing:.04em;color:inherit;opacity:0}}
.lsdet{{display:inline-flex;gap:8px;font:600 calc(var(--fs) * .66)/1 var(--fb);color:inherit;opacity:.84}}
.lsdet span{{opacity:0}}
.lstag{{position:absolute;right:0;top:50%;margin-top:-19px;height:38px;display:inline-flex;align-items:center;padding:0 16px;border-radius:999px;
  background:{c['accent2']};color:var(--ink);font:800 22px/1 var(--fd);letter-spacing:.06em;text-transform:uppercase;opacity:0;
  transform-origin:100% 50%;box-shadow:0 6px 16px rgba(29,18,20,.18)}}
/* ACTIVE: emphasis colour (the fill layer wipes in), cream badge */
.lsr.active .lsc{{outline:3px solid {c['highlight']};outline-offset:-3px;
  box-shadow:0 0 0 5px rgba(233,205,126,.35),0 0 46px rgba(122,30,46,.55),0 18px 40px rgba(122,30,46,.4)}}
.lsr.active .lsc::after{{content:"";position:absolute;left:0;top:0;bottom:0;width:10px;background:{c['highlight']}}}
.lsr.active .lsb{{background:#F6F2EE;border-color:#F6F2EE;color:var(--accent)}}
.lsr.active .lsph{{background:rgba(246,242,238,.25)}}
/* DONE: calm, compressed about the badge */
.lsr.done .lsc{{background:rgba(255,255,255,.94);outline-color:transparent}}
.lsr.done .lsb{{background:var(--ink);border-color:var(--ink);color:#F6F2EE}}
.lsr.done .lsdet{{opacity:.66}}
"""
