"""CLEAN TALK style: the speaker full frame and natural, one white word at a time at chest height (soft shadow, no
box), a small 3-line opening headline with the middle line in the emphasis color, one or two typography moments
(a big keyword in the emphasis color with smaller connecting words, captions hidden while it shows) and one or two
small rounded info cards in the free space above the shoulders. Gentle push / pull zooms across whole phrases only.
Modeled on a clean "talking head + minimal type" creator look. Voice only by default.

Loaded by templates/split/compose.py when project.json has "style": "clean-talk". Everything else (cuts, punch-ins,
caption chunking, QA boxes) is the split engine. See README.md in this folder for the project.json shape.

Overlay inserts (project.json "overlays", each with from/until):
  ct_headline  3 stacked lines, `em` line index in the emphasis color, eased staggered entrance, eased exit
  ct_type      typography moment: small lines + one big keyword line, each word revealed on its spoken word
  ct_card      small rounded card: kicker + rows that tick in on their words (credentials, checklists)
  ct_lab       small rounded lab-value card: kicker, a range bar with a threshold, a marker that slides past it, a flag
  ct_push      gentle push / pull on the speaker across a whole phrase (scale about the face centre, >= 1.0 always)
"""
import json
import os
import re

from ctx import esc, snap

DEFAULTS = {
    "captions": {"mode": "word", "strip_punct": True, "accent": [], "no_repeat": False},  # ct_type hides captions itself
    "head_margin": 28,
    "fonts_load": ['800 76px "Inter Tight"', '900 150px "Inter Tight"', '700 30px "Inter"'],
}

EM = "#F2CF7A"          # warm gold emphasis: reads over the bright wall and the white shirt (see README)
CAP_MIN, CAP_MAX = 1236, 1370
CAP_GAP = 34            # px between the chin (tracked) and the caption's top
SIDE = 60               # card inset from the frame edge (safe side is 35)
ROW_H = 66              # card row height
FLAG_H = 78             # lab card flag row height


# ----------------------------------------------------------------------------- helpers
def _words(text):
    return [w for w in str(text).split(" ") if w]


def _band_top(a, h, prefer=None):
    y0, y1 = a.get("_area", (220, 760))
    top = prefer if prefer is not None else y0 + 70
    if top + h > y1:
        top = max(y0, y1 - h)
    return round(top)


def _exit(cx, sel, t, dur=0.32, dy=-10):
    cx.to(sel, t, {"opacity": 0, "y": dy, "filter": "blur(6px)"}, dur=dur, ease="power2.in")


def _caps(cx, t, on):
    """Hide / show every caption (a CSS variable on the root: seek-safe tl.set)."""
    cx.set("#root", t, {"--capvis": 1 if on else 0})


def word_cap_top(cx, c, layout):
    chin = cx.chin(c["t0"], c["t1"])
    if chin is None:
        return CAP_MIN
    return round(min(max(CAP_MIN, chin + CAP_GAP), CAP_MAX))


# ----------------------------------------------------------------------------- motion helpers (motion v2 phase 3)
def _js(cx, line):
    cx.tw.append(line)


def _ft(cx, sel, t, frm, to, dur, ease, stagger=None):
    """fromTo that never shows its from-state early (immediateRender false); eases are motion tokens."""
    v = dict(to, duration=dur, ease=ease, immediateRender=False)
    if stagger:
        v["stagger"] = stagger
    _js(cx, f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(v)},{snap(t)});")


def _push(cx, sel, t, dur=0.42, frm=110, opacity=None, t_hide=None):
    """The line pushes up through an em mask (RRM.mask), hidden from its own frame; the mask opens (overflow visible)
    once it lands so the soft text shadow is never clipped while it holds. frm < 110 starts it part-way risen."""
    # a fully hidden line is also transparent until it pushes: the mask's shadow padding would show its top otherwise
    o0, o1 = (",opacity:0", ",opacity:1") if frm >= 100 else ("", "")
    o = "" if opacity is None else f"tl.fromTo(e,{{opacity:{opacity}}},{{opacity:1,duration:{dur},ease:'expo.out',immediateRender:false}},{snap(t)});"
    _js(cx, f"(function(){{var e=document.querySelector({json.dumps(sel)}),i=RRM.mask(e),m=i.parentNode;"
            f"tl.set(i,{{yPercent:{frm}{o0}}},{snap(t if t_hide is None else min(t, t_hide))});"
            f"tl.set(e,{{autoAlpha:1}},{snap(t)});tl.set(m,{{overflow:'hidden'}},{snap(t if t_hide is None else min(t, t_hide))});"
            f"tl.fromTo(i,{{yPercent:{frm}{o0},filter:'blur(6px)'}},{{yPercent:0{o1},filter:'blur(0px)',duration:{dur},ease:'expo.out',"
            f"immediateRender:false}},{snap(t)});{o}tl.set(m,{{overflow:'visible'}},{snap(t + dur)});}})();")


def _letters(cx, sel, t, stagger=2 / 30, dur=0.22):
    """Each letter stamps in from oversize, two frames apart (RRM letterStamp), with a short blur."""
    _js(cx, f"RRM.enter('letterStamp',tl,document.querySelector({json.dumps(sel)}),{snap(t)},"
            f"{{stagger:{stagger:.4f},dur:{dur},from:1.38}});")


def _drift(cx, sel, t0, t1, amp=5, period=1.8, seed=0):
    """Idle float while a card holds: a slow sine bob plus a hair of rotation, on its own wrapper (no fights)."""
    span = t1 - t0
    if span < period:
        return
    reps = max(0, int(span / period) - 1)
    rot = 0.6 if seed % 2 == 0 else -0.6
    _js(cx, f'tl.fromTo({json.dumps(sel)},{{y:0,rotation:0}},{{y:{-amp},rotation:{rot},duration:{period},ease:"sine.inOut",'
            f'yoyo:true,repeat:{reps},immediateRender:false}},{snap(t0)});')


def _card_in(cx, b, sel, t, side):
    """A card lands with depth: swings in from its side in 3D (rotationY + z + blur), overshoots a hair and settles."""
    k = -1 if side == "left" else 1
    cx.enter(b, sel, t, {"opacity": 0, "x": 90 * k, "y": 16, "rotationY": 34 * k, "rotationX": 8, "z": -160, "scale": 0.92,
                         "filter": "blur(12px)", "transformPerspective": 1100},
             {"opacity": 1, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0, "scale": 1, "filter": "blur(0px)",
              "transformPerspective": 1100}, dur=0.62, ease="back.out(1.4)")


def _card_out(cx, sel, t, side, dur=0.26):
    k = -1 if side == "left" else 1
    cx.to(sel, t, {"opacity": 0, "x": 40 * k, "rotationY": 18 * k, "scale": 0.96, "filter": "blur(8px)",
                   "transformPerspective": 1100}, dur=dur, ease="power3.in")


CALM_MOVES = ["zoom", "iris"]   # clean-talk's transitions (section cuts only): a zoom-through or a circle reveal, never a whip


def _section(cx, a):
    """args.section: "#seg" (or a list) = that cut opens a new section (hook -> credentials -> item 1 ...). The engine
    motion layer may give it a calm transition (level budget). Once per project the move set is narrowed to CALM_MOVES
    unless project.json motion.transitions names its own moves."""
    secs = a.get("section")
    if not secs:
        return
    secs = [secs] if isinstance(secs, str) else list(secs)
    cx.section_cuts = set(getattr(cx, "section_cuts", None) or ()) | {str(x).lstrip("#") for x in secs}
    m = getattr(cx, "motion_cfg", None)
    if m is not None and not getattr(cx, "_ct_moves", False):
        cx._ct_moves = True
        try:
            pj = json.load(open(os.path.join(cx.dir, "project.json")))
        except (OSError, ValueError):
            pj = {}
        tr = (pj.get("motion") or {}).get("transitions") if isinstance(pj.get("motion"), dict) else None
        if not (isinstance(tr, dict) and tr.get("moves")):
            m["moves"] = list(CALM_MOVES)


# ----------------------------------------------------------------------------- inserts
def ct_headline(cx, b, a):
    """3 stacked lines; args: lines [l1, l2, l3] (each a string or {"text", "at": "@word"}), em (index, default 1),
    y (top px), stagger (used for lines without `at`).
    Each line pushes up through a mask; the emphasis line sweeps in gold from the left with a soft blur and a glint.
    Frame 0 is never empty: a headline starting at 0 begins part-way risen."""
    _section(cx, a)
    hid, t0, t1 = cx.uid("hd"), b["t0"], b["t1"]
    lines = a.get("lines", [])
    em = int(a.get("em", 1))
    h = 76 * len(lines)
    top = _band_top(a, h, a.get("y"))
    parts = []
    stag = float(a.get("stagger", 0.14))
    for i, ln in enumerate(lines):
        lid = f"{hid}l{i}"
        ti = t0 + stag * i
        if isinstance(ln, dict):          # {"text", "at": "@word"}: the line lands on its spoken word
            ti = cx.cue(ln["at"], b, lead="type", fallback=stag * i) if ln.get("at") else ti
            ln = ln.get("text", "")
        if i == em:
            parts.append(f'<div class="cthl em" id="{lid}" data-fit="900,40" {cx.box("text", t0, t1, True)}>'
                         f'<span class="ctsw" id="{lid}s">{esc(ln)}</span></div>')
            ti += 0.08 if ti < t0 + 0.05 * (i + 1) else 0
            cx.set(f"#{lid}", t0, {"autoAlpha": 1})
            cx.set(f"#{lid}s", t0, {"clipPath": "inset(-30% 100% -40% -4%)"})   # hidden until its sweep
            _ft(cx, f"#{lid}s", ti, {"clipPath": "inset(-30% 100% -40% -4%)", "x": -26, "filter": "blur(8px)"},
                {"clipPath": "inset(-30% -4% -40% -4%)", "x": 0, "filter": "blur(0px)"}, 0.56, "expo.inOut")
            cx.event(ti + 0.2, "whoosh", "headline gold sweep")
        else:
            parts.append(f'<div class="cthl" id="{lid}" data-fit="900,40" {cx.box("text", t0, t1, True)}>{esc(ln)}</div>')
            first = ti < 0.05
            _push(cx, f"#{lid}", ti, dur=0.5, frm=55 if first else 110, opacity=0.45 if first else None, t_hide=t0)
            cx.event(ti, "click", f"headline line {i + 1}")
        _js(cx, f'tl.to("#{lid}",{{opacity:0,y:-14,filter:"blur(6px)",duration:0.22,ease:"power3.in"}},{snap(t1 - 0.3 + 0.04 * i)});')
    return f'<div class="cthead" id="{hid}" style="top:{top}px">{"".join(parts)}</div>'


def ct_type(cx, b, a):
    """Typography moment. args: lines [{"text", "at" (first word's anchor), "big": bool}], y, hide_until, hold.
    Small words snap up on their own spoken words; the big keyword stamps in letter by letter in gold on its word,
    with a gentle push toward the viewer while it holds. Captions are hidden from the first word until `hide_until`."""
    _section(cx, a)
    tid, t0, t1 = cx.uid("ty"), b["t0"], b["t1"]
    lines = a.get("lines", [])
    h = sum(150 if ln.get("big") else 64 for ln in lines) + 12 * (len(lines) - 1)
    top = _band_top(a, h, a.get("y"))
    html = []
    for li, ln in enumerate(lines):
        cls = "ctbig" if ln.get("big") else "ctsm"
        spans = []
        lo = cx.when(ln.get("at"), b, 0.0)
        for wi, w in enumerate(_words(ln["text"])):
            wid = f"{tid}l{li}w{wi}"
            key = re.sub(r"[^\w']+", "", w.lower())
            tw = cx.words.find(key, lo - 0.02, t1 + 0.5) if key else None
            tw = lo if tw is None else tw
            lo = tw + 0.01
            if ln.get("big"):
                _letters(cx, f"#{wid}", tw - 0.03)
                cx.event(tw - 0.03, "pop", f"keyword {w}")
            else:
                cx.enter(b, f"#{wid}", tw - 0.04, {"opacity": 0, "y": 26, "filter": "blur(6px)"},
                         {"opacity": 1, "y": 0, "filter": "blur(0px)"}, dur=0.22, ease="expo.out")
                if wi == 0:
                    cx.event(tw - 0.04, "click", "typography line")
            spans.append(f'<span class="ctw" id="{wid}">{esc(w)}</span>')
        bid = f"{tid}l{li}"
        html.append(f'<div class="{cls}" id="{bid}" data-fit="{960 if ln.get("big") else 900},30" {cx.box("text", t0, t1, True)}>'
                    f'{" ".join(spans)}</div>')
        if ln.get("big"):   # the keyword leans toward the viewer while it holds (slow, calm)
            tb = cx.when(ln.get("at"), b, 0.0)
            _ft(cx, f"#{bid}", tb, {"scale": 1}, {"scale": 1.06}, max(0.6, t1 - tb), "sine.inOut")
    _caps(cx, t0, False)
    hide_until = cx.when(a.get("hide_until"), b, t1 - b["t0"]) if a.get("hide_until") else t1
    _caps(cx, hide_until, True)
    if not a.get("hold"):
        _exit(cx, f"#{tid}", t1 - 0.3, dur=0.24)
    return f'<div class="cttype" id="{tid}" style="top:{top}px">{"".join(html)}</div>'


WARN = ('<svg viewBox="0 0 24 24" width="26" height="26"><path d="M12 7v6" stroke="currentColor" stroke-width="3" '
        'stroke-linecap="round"/><circle cx="12" cy="17.4" r="1.8" fill="currentColor"/></svg>')


def _tick(pid):
    return (f'<svg viewBox="0 0 24 24" width="22" height="22"><path id="{pid}" pathLength="1" d="M5.5 12.5l4 4 9-9.5" fill="none" '
            'stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" '
            'style="stroke-dasharray:1;stroke-dashoffset:1"/></svg>')


def ct_card(cx, b, a):
    """Small rounded card. args: side (left|right), kicker, rows [{"text", "at"}], w, y.
    The card swings in with depth (3D, blur, a small overshoot) and floats while it holds; each row grows in on its
    word: the tick pops and draws, the text pushes up through a mask. QA gets the final box through cx.extra_boxes."""
    _section(cx, a)
    kid, t0, t1 = cx.uid("cd"), b["t0"], b["t1"]
    rows = a.get("rows", [])
    w = int(a.get("w", 520))
    side = a.get("side", "left")
    h_final = 26 + 46 + ROW_H * len(rows) + 22
    top = _band_top(a, h_final, a.get("y"))
    left = SIDE if side == "left" else 1080 - SIDE - w
    _card_in(cx, b, f"#{kid}", t0, side)
    _drift(cx, f"#{kid}w", t0 + 0.6, t1 - 0.3, seed=0 if side == "left" else 1)
    cx.event(t0, "whoosh", "card lands")
    out = []
    for i, r in enumerate(rows):
        rid = f"{kid}r{i}"
        tr = max(t0 + 0.12, cx.cue(r.get("at"), b, lead="visual", fallback=0.15 + 0.4 * i) if r.get("at") else t0 + 0.15 + 0.4 * i)
        cx.to(f"#{rid}", tr - 0.06, {"height": ROW_H}, dur=0.34, ease="expo.out")
        cx.enter(b, f"#{rid}k", tr, {"opacity": 0, "scale": 0.3, "rotation": -30}, {"opacity": 1, "scale": 1, "rotation": 0},
                 dur=0.34, ease="back.out(2.2)")
        _js(cx, f"RRM.enter('drawOn',tl,document.querySelector('#{rid}p'),{snap(tr + 0.08)},{{dur:0.26}});")
        _push(cx, f"#{rid}t", tr + 0.03, dur=0.34)
        cx.event(tr, "tick", f"card row {r['text']}")
        out.append(f'<div class="ctrow" id="{rid}"><div class="ctri"><span class="ctk" id="{rid}k">{_tick(rid + "p")}</span>'
                   f'<span class="ctrt" id="{rid}t" data-fit="{w - 120},26" {cx.box("text", max(tr, t0), t1, True)}>{esc(r["text"])}</span></div></div>')
    _card_out(cx, f"#{kid}", t1 - 0.3, side)
    cx.extra_boxes.append({"kind": "card", "x": left, "y": top, "w": w, "h": h_final, "t0": t0, "t1": t1,
                           "text": "card (final)", "readable": False})
    kick = f'<div class="ctkick" {cx.box("text", t0, t1, True)}>{esc(a.get("kicker", ""))}</div>' if a.get("kicker") else ""
    return (f'<div class="ctdw" id="{kid}w" style="left:{left}px;top:{top}px;width:{w}px">'
            f'<div class="ctcard" id="{kid}" {cx.box("card", t0, t1)}>{kick}{"".join(out)}</div></div>')


def ct_lab(cx, b, a):
    """Lab-value card. args: side, kicker, unit, lo_label, hi_label, threshold ("7"), slide_at, mark_at, flag, flag_at, w, y.
    The card swings in with depth and floats; the marker slides from the low zone past the threshold on `slide_at`
    (it squashes as it arrives), the high zone floods in, the threshold number stamps on `mark_at`, the flag pops in
    under the bar on `flag_at`."""
    _section(cx, a)
    lid, t0, t1 = cx.uid("lb"), b["t0"], b["t1"]
    w = int(a.get("w", 560))
    h_final = 26 + 46 + 34 + 64 + FLAG_H + 24
    top = _band_top(a, h_final, a.get("y"))
    side = a.get("side", "right")
    left = SIDE if side == "left" else 1080 - SIDE - w
    bar_w = w - 64
    _card_in(cx, b, f"#{lid}", t0, side)
    _drift(cx, f"#{lid}w", t0 + 0.6, t1 - 0.3, seed=1)
    cx.event(t0, "whoosh", "lab card lands")
    ts = cx.cue(a.get("slide_at"), b, lead="visual", fallback=1.0) if a.get("slide_at") else t0 + 1.0
    tm = cx.cue(a.get("mark_at"), b, lead="stamp", fallback=1.3) if a.get("mark_at") else t0 + 1.3
    tf = cx.cue(a.get("flag_at"), b, lead="visual", fallback=2.0) if a.get("flag_at") else t0 + 2.0
    x0, x1 = round(bar_w * 0.24), round(bar_w * 0.8)
    cx.set(f"#{lid}m", t0, {"x": x0})
    cx.to(f"#{lid}m", ts, {"x": x1}, dur=0.62, ease="expo.inOut")
    _js(cx, f"RRM.squash(tl,'#{lid}m',{snap(ts + 0.5)},{{k:0.78,origin:'50% 50%'}});")
    _ft(cx, f"#{lid}hi", ts + 0.24, {"opacity": 0, "scaleX": 0}, {"opacity": 1, "scaleX": 1}, 0.5, "expo.out")
    cx.enter(b, f"#{lid}t", tm, {"opacity": 0.4, "scale": 1.9, "filter": "blur(8px)"}, {"opacity": 1, "scale": 1, "filter": "blur(0px)"},
             dur=0.22, ease="power4.out")
    cx.to(f"#{lid}fw", tf - 0.05, {"height": FLAG_H}, dur=0.34, ease="expo.out")
    cx.enter(b, f"#{lid}f", tf, {"opacity": 0, "scale": 0.5, "y": 12}, {"opacity": 1, "scale": 1, "y": 0}, dur=0.36, ease="back.out(2.2)")
    cx.event(ts, "whoosh", "lab marker")
    cx.event(tm, "pop", "lab threshold")
    cx.event(tf, "pop", "lab flag")
    _card_out(cx, f"#{lid}", t1 - 0.3, side)
    cx.extra_boxes.append({"kind": "card", "x": left, "y": top, "w": w, "h": h_final, "t0": t0, "t1": t1,
                           "text": "lab card (final)", "readable": False})
    thr = esc(a.get("threshold", "7"))
    return (f'<div class="ctdw" id="{lid}w" style="left:{left}px;top:{top}px;width:{w}px">'
            f'<div class="ctcard ctlab" id="{lid}" {cx.box("card", t0, t1)}>'
            f'<div class="ctkick" {cx.box("text", t0, t1, True)}>{esc(a.get("kicker", "FASTING INSULIN"))}'
            f'<span class="ctunit">{esc(a.get("unit", ""))}</span></div>'
            f'<div class="ctbar" style="width:{bar_w}px"><div class="ctlo"></div><div class="cthi" id="{lid}hi"></div>'
            f'<div class="ctthr"></div><div class="ctmark" id="{lid}m"></div></div>'
            f'<div class="ctscale" style="width:{bar_w}px"><span {cx.box("text", t0, t1, True)}>{esc(a.get("lo_label", "Under"))}</span>'
            f'<span class="ctt" id="{lid}t" {cx.box("text", max(tm, t0), t1, True)}>{thr}</span>'
            f'<span {cx.box("text", t0, t1, True)}>{esc(a.get("hi_label", "Over"))}</span></div>'
            f'<div class="ctfw" id="{lid}fw"><div class="ctflag" id="{lid}f" {cx.box("text", max(tf, t0), t1, True)}>'
            f'{WARN}{esc(a.get("flag", ""))}</div></div></div></div>')


def ct_push(cx, b, a):
    """Gentle push / pull across a phrase: #sp scales about the face centre of segment `seg` (from work/facepos.json)
    from `s0` to `s1` (both >= 1, so no edge ever shows) between the overlay's from/until; reset to 1 at `until`."""
    fp = {}
    p = os.path.join(cx.dir, "work", "facepos.json")
    if os.path.exists(p):
        fp = json.load(open(p)).get(a.get("seg", ""), {})
    ox, oy = fp.get("cx", 540), fp.get("cy", 1000)
    s0, s1 = float(a.get("s0", 1.0)), float(a.get("s1", 1.05))
    if min(s0, s1) < 1.0:
        cx.warn("ct_push: scale below 1.0 would show frame edges; clamped")
        s0, s1 = max(1.0, s0), max(1.0, s1)
    t0, t1 = b["t0"], b["t1"]
    v0 = {"scale": s0, "transformOrigin": f"{ox}px {oy}px"}
    v1 = {"scale": s1, "duration": round(t1 - t0, 3), "ease": "sine.inOut", "immediateRender": False}
    cx.tw.append(f'tl.fromTo("#sp",{json.dumps(v0)},{json.dumps(v1)},{snap(t0)});')
    cx.set("#sp", t1, {"scale": 1})
    return ""


INSERTS = {"ct_headline": ct_headline, "ct_type": ct_type, "ct_card": ct_card, "ct_lab": ct_lab, "ct_push": ct_push}


def css(brand, cx):
    c = brand["colors"]
    sh = "0 1px 2px rgba(0,0,0,.55),0 3px 10px rgba(0,0,0,.40),0 8px 34px rgba(0,0,0,.32)"
    return f"""
#root{{--capvis:1;--em:{EM}}}
.cap.wcap .pill{{background:none;padding:0;border-radius:0;font:800 76px/1.1 var(--fd);letter-spacing:-.022em;color:#fff;
  text-shadow:{sh};opacity:var(--capvis)}}
.cap.wcap.wpill .pill{{background:none;padding:0 12px}}
.cthead{{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center;gap:2px}}
.cthl{{font:800 62px/1.12 var(--fd);letter-spacing:-.02em;word-spacing:.035em;color:#fff;white-space:nowrap;text-shadow:{sh}}}
.cthl.em{{color:var(--em)}}
.ctsw{{display:inline-block}}
.cthl .rm-mask{{padding:.2em .4em .45em;margin:-.2em -.4em -.45em}}
.ctbig .rc{{transform-origin:50% 85%}}
.cttype{{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center;gap:12px}}
.ctsm{{font:700 52px/1.2 var(--fd);letter-spacing:-.015em;color:#fff;white-space:nowrap;text-shadow:{sh}}}
.ctbig{{font:900 150px/1 var(--fd);letter-spacing:-.03em;word-spacing:.07em;color:var(--em);white-space:nowrap;
  text-shadow:0 2px 3px rgba(0,0,0,.35),0 8px 30px rgba(0,0,0,.35),0 18px 60px rgba(0,0,0,.22)}}
.ctw{{display:inline-block;opacity:0}}
.ctdw{{position:absolute;transform-origin:50% 0}}
.ctcard{{position:relative;background:rgba(255,255,255,.97);border-radius:32px;padding:26px 32px 22px;
  box-shadow:0 22px 50px rgba(20,12,14,.22),0 4px 12px rgba(20,12,14,.10)}}
.ctkick{{display:flex;align-items:center;gap:14px;height:28px;margin-bottom:18px;font:800 26px/1 var(--fb);letter-spacing:.14em;
  text-transform:uppercase;color:{c['accent']};white-space:nowrap}}
.ctunit{{font:600 22px/1 var(--fb);letter-spacing:.01em;text-transform:none;color:rgba(29,18,20,.45)}}
.ctrow{{height:0;overflow:hidden}}
.ctri{{display:flex;align-items:center;gap:18px;height:{ROW_H}px}}
.ctk{{flex:none;width:42px;height:42px;border-radius:50%;background:{c['accent']};color:#fff;display:flex;align-items:center;justify-content:center}}
.ctk svg{{width:24px;height:24px}}
.ctrt{{font:700 40px/1 var(--fd);letter-spacing:-.02em;word-spacing:.04em;color:{c['ink']};white-space:nowrap}}
.ctbar{{position:relative;height:30px;border-radius:15px;background:rgba(29,18,20,.12);margin-top:12px}}
.cthi{{position:absolute;left:50%;right:0;top:0;bottom:0;border-radius:0 15px 15px 0;background:{c['accent']};opacity:.22;transform-origin:0 50%}}
.ctthr{{position:absolute;left:50%;top:-9px;bottom:-9px;width:5px;margin-left:-2.5px;border-radius:3px;background:{c['ink']}}}
.ctmark{{position:absolute;left:0;top:50%;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;background:#fff;
  border:9px solid {c['accent']};box-shadow:0 5px 14px rgba(122,30,46,.38)}}
.ctscale{{position:relative;height:64px;display:flex;justify-content:space-between;align-items:center;
  font:700 30px/1 var(--fb);color:rgba(29,18,20,.55)}}
.ctscale .ctt{{position:absolute;left:50%;top:6px;width:100px;margin-left:-50px;text-align:center;
  font:900 58px/1 var(--fd);letter-spacing:-.03em;color:{c['ink']}}}
.ctfw{{height:0;overflow:hidden}}
.ctflag{{word-spacing:.05em;display:inline-flex;align-items:center;gap:10px;height:62px;margin-top:12px;padding:0 28px 0 20px;border-radius:999px;
  background:{c['accent']};color:#fff;font:800 34px/1 var(--fd);letter-spacing:-.015em;white-space:nowrap}}
"""
