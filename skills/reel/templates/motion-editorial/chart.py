"""cycle_chart: the "crash out and bounce back" curve for MOTION EDITORIAL, built step by step on spoken words.

Deterministic SVG + GSAP (no AI): a baseline, a deep V at the crash point, a recovery back to baseline, then a branch up
(higher new baseline) or down (lower new baseline). Brackets measure the 4 parts; 4 numbered slots under the chart
follow the list rules (fixed scaffold, revealed as spoken, active one highlighted, numbers never move) and the insert
writes the plan to cx.list_plan (compose saves it as work/list.json for qa.py list_rules).

args (every time is an anchor: number = s after the beat start, "@word", "#seg" = that cut's first frame):
  mode       "cycle" (default) | "unbreakable" (full curve shown, then the tolerance line stretches right and holds)
  ghost_at   faint dotted preview of the whole curve draws in          title {l1, l2, l1_at, l2_at, kicker, kicker_at, kicker_until}
  slots      [{label, at}] x4 (scaffold shows from slots_at)            steps {name: anchor} for every chart element:
             base, tol_bracket, icons [a,a,a,a] (bill, traffic light, argument, alarm clock), marks [a..], crash_dot, descent, depth_bracket, fortitude, recovery, recovery_end, res_bracket,
             resilience, watch, return_dot, up, high, down, low, adaptability, you, you_stop, improve
  flash      {src, at, dur, media_start, box, video} silent inset clip on a word (~1 s)
  ghost_from {src, size, pos, h}  a still of the previous shot that shrinks away on the first frame (hook -> chart hand-off)
  unbreakable mode: stretch_at, word_at, word
"""
import json
import math

from ctx import esc, snap

# geometry (frame px)
X0, XC, B = 70, 450, 390          # baseline start, crash point, baseline y
XD, D = 530, 580                  # dip bottom
XR, XE = 790, 1010                # back at baseline, branch end
UP, LO = 310, 470                 # new baselines after the branch
P_BASE = f"M{X0},{B} L{XC},{B}"
P_DESC = f"M{XC},{B} L{XD},{D}"
P_REC = f"M{XD},{D} C{XD + 60},{D} {XR - 80},{B + 12} {XR},{B}"
P_UP = f"M{XR},{B} C{XR + 50},{B} {XR + 70},{UP} {XR + 130},{UP} L{XE},{UP}"
P_LO = f"M{XR},{B} C{XR + 50},{B} {XR + 70},{LO} {XR + 130},{LO} L{XE},{LO}"
SLOT_Y, SLOT_W, SLOT_H, SLOT_X0, SLOT_GAP = 684, 240, 96, 45, 10
YOU_W, YOU_BELOW, YOU_ABOVE, YOU_DX = 112, 46, -92, 39   # YOU? pill: under the dot on the line, inside the V at the dip
CIRCLE = 54


def _bez(p0, p1, p2, p3, n=24):
    out = []
    for i in range(1, n + 1):
        u = i / n
        out.append(tuple((1 - u) ** 3 * a + 3 * (1 - u) ** 2 * u * b + 3 * (1 - u) * u ** 2 * c + u ** 3 * d
                         for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def curve_points():
    """The main line (baseline, V, recovery, up branch) as a dense polyline, for the YOU? glide."""
    pts = [(X0, B), (XC, B), (XD, D)]
    pts += _bez((XD, D), (XD + 60, D), (XR - 80, B + 12), (XR, B))
    return pts


def _arc(pts):
    acc = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.hypot(bx - ax, by - ay))
    return acc


def _point_at(pts, acc, s):
    for i in range(1, len(acc)):
        if acc[i] >= s:
            k = (s - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-6)
            return (pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k)
    return pts[-1]


def _draw(cx, beat, sel, t, dur=0.5, ease="power2.inOut"):
    cx.enter(beat, sel, t, {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, dur=dur, ease=ease)


def _rise(cx, beat, sel, t, dy=18, dur=0.3):
    cx.enter(beat, sel, t, {"opacity": 0, "y": dy}, dur=dur)


def _pop(cx, beat, sel, t, dur=0.3):
    cx.enter(beat, sel, t, {"opacity": 0, "scale": 0.4, "transformOrigin": "50% 50%"},
             {"opacity": 1, "scale": 1, "transformOrigin": "50% 50%"}, dur=dur, ease="back.out(2)")


def _path(pid, d, cls, hidden=True):
    dash = ' pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"' if hidden else ""
    return f'<path id="{pid}" class="{cls}" d="{d}"{dash}/>'


def _label(cx, beat, lid, text, x, y, t, align="center", cls="cl", span=520):
    """Text anchored at x (centre / right edge / left edge) without CSS transforms (GSAP owns the transforms)."""
    left = {"center": x - span // 2, "right": x - span, "left": x}[align]
    return (f'<div class="lab {align}" id="{lid}" style="left:{left}px;top:{y}px;width:{span}px">'
            f'<span class="{cls}" {cx.box("text", max(t, beat["t0"]), beat["t1"], True)}>{esc(text)}</span></div>')


def _bracket_h(x0, x1, y, tick=9):
    return f"M{x0},{y - tick} L{x0},{y + tick} M{x0},{y} L{x1},{y} M{x1},{y - tick} L{x1},{y + tick}"


def _bracket_v(x, y0, y1, tick=9):
    return f"M{x - tick},{y0} L{x + tick},{y0} M{x},{y0} L{x},{y1} M{x - tick},{y1} L{x + tick},{y1}"


BOLT = "M0,-20 L-7,2 L-1,2 L-5,20 L8,-4 L2,-4 L6,-20 Z"
# "bad things" line icons, 40 px, origin = bottom centre (they stand on the baseline). Deterministic SVG, no text.
ICONS = {
    "bill": ('<path class="ib" d="M-13,-38 L13,-38 L13,-5 L9,-9 L5,-5 L1,-9 L-3,-5 L-7,-9 L-11,-5 L-13,-7 Z"/>'
             '<path class="il" d="M-8,-30 L8,-30 M-8,-23 L8,-23 M-8,-16 L3,-16"/>'),
    "light": ('<rect class="ib" x="-10" y="-41" width="20" height="39" rx="6"/>'
              '<circle class="if" cx="0" cy="-32" r="4.5"/><circle class="il" cx="0" cy="-21.5" r="4.5"/>'
              '<circle class="il" cx="0" cy="-11" r="4.5"/>'),
    "argue": ('<path class="ib" d="M-20,-39 h20 a5,5 0 0 1 5,5 v8 a5,5 0 0 1 -5,5 h-12 l-6,6 v-6 h-2 a5,5 0 0 1 -5,-5 v-8 a5,5 0 0 1 5,-5 Z"/>'
              '<path class="ib" d="M2,-27 h16 a5,5 0 0 1 5,5 v8 a5,5 0 0 1 -5,5 h-1 v6 l-6,-6 h-9 a5,5 0 0 1 -5,-5 v-8 a5,5 0 0 1 5,-5 Z"/>'
              '<path class="il" d="M-10,-35 v6 M-10,-25.5 v0.5 M10,-23 v6 M10,-13.5 v0.5"/>'),
    "clock": ('<path class="il" d="M-15,-29 a7,7 0 0 1 9,-9 M15,-29 a7,7 0 0 0 -9,-9 M-9,-6 L-12,-1 M9,-6 L12,-1"/>'
              '<circle class="ib" cx="0" cy="-19" r="14"/><path class="il" d="M0,-19 L0,-27 M0,-19 L6,-15"/>'),
}
ICON_ORDER = ("bill", "light", "argue", "clock")
ICON_SCALE = 1.35   # 54 px on the 1080 frame: about 20 pt on a phone
WATCH = ('<circle cx="0" cy="2" r="17" class="wf"/><path d="M-5,-20 L5,-20 M0,-20 L0,-15" class="wk"/>'
         '<path id="{hid}" d="M0,2 L0,-10" class="wh"/>')


def _steps(cx, beat, a, uid, svg, html):
    """The cycle steps (each element hidden until its word)."""
    st = a.get("steps", {})
    w = lambda k, d=None: cx.when(st[k], beat, 0) if st.get(k) is not None else d  # noqa: E731
    if w("base") is not None:
        svg.append(_path(f"{uid}base", P_BASE, "ln"))
        _draw(cx, beat, f"#{uid}base", w("base"), 0.8, "power1.inOut")
        cx.event(w("base"), "scribble", "chart baseline")
    if w("tol_bracket") is not None:
        t = w("tol_bracket")
        svg.append(_path(f"{uid}tb", _bracket_h(X0, XC, B - 82), "br"))
        _draw(cx, beat, f"#{uid}tb", t, 0.45)
        html.append(_label(cx, beat, f"{uid}tl", "tolerance", X0, B - 156, t, "left"))   # clear of the kicker
        _rise(cx, beat, f"#{uid}tl", t + 0.12)
    icons = st.get("icons") or []
    for i, m in enumerate(icons):   # bad things land on the baseline one after another, on their words
        t = cx.when(m, beat, 0)
        x = X0 + 50 + i * (XC - X0 - 80) / max(len(icons) - 1, 1)
        kind = ICON_ORDER[i % len(ICON_ORDER)]
        svg.append(f'<g transform="translate({x:.0f},{B - 9}) scale({ICON_SCALE})"><g id="{uid}i{i}" class="icon">{ICONS[kind]}</g></g>')
        cx.enter(beat, f"#{uid}i{i}", t, {"opacity": 0, "y": -70}, {"opacity": 1, "y": 0}, dur=0.4, ease="bounce.out")
        cx.event(t, "tick", f"icon {kind}")
    for i, m in enumerate(st.get("marks", [])):
        t = cx.when(m, beat, 0)
        x = X0 + 85 + i * 105
        svg.append(f'<g transform="translate({x},{B - 2})"><g id="{uid}m{i}" class="bolt"><path d="{BOLT}"/></g></g>')
        cx.enter(beat, f"#{uid}m{i}", t, {"opacity": 0, "y": -46}, {"opacity": 1, "y": 0}, dur=0.3, ease="bounce.out")
    if w("crash_dot") is not None:
        t = w("crash_dot")
        svg.append(f'<g id="{uid}cd"><circle cx="{XC}" cy="{B}" r="15" class="dot"/><circle cx="{XC}" cy="{B}" r="5" class="dotc"/></g>'
                   f'<circle id="{uid}cr" cx="{XC}" cy="{B}" r="15" class="ring"/>')
        _pop(cx, beat, f"#{uid}cd", t)
        cx.tw.append(f'tl.fromTo("#{uid}cr",{{opacity:0.9,attr:{{r:15}}}},{{opacity:0,attr:{{r:48}},duration:0.6,'
                     f'ease:"power2.out",immediateRender:false}},{snap(t)});')
    if w("descent") is not None:
        svg.append(_path(f"{uid}de", P_DESC, "ln"))
        _draw(cx, beat, f"#{uid}de", w("descent"), 0.38, "power2.in")
    if w("depth_bracket") is not None:
        svg.append(_path(f"{uid}db", _bracket_v(XC - 30, B, D), "br"))
        _draw(cx, beat, f"#{uid}db", w("depth_bracket"), 0.45)
    if w("fortitude") is not None:
        html.append(_label(cx, beat, f"{uid}fl", "fortitude", XC - 54, D - 104, w("fortitude"), "right"))
        _rise(cx, beat, f"#{uid}fl", w("fortitude"))
    _steps_recovery(cx, beat, w, uid, svg, html)
    _steps_branch(cx, beat, w, uid, svg, html)


def _steps_recovery(cx, beat, w, uid, svg, html):
    if w("recovery") is not None:
        svg.append(_path(f"{uid}re", P_REC, "ln"))
        end = w("recovery_end")    # optional: the climb reaches the baseline exactly on this word
        _draw(cx, beat, f"#{uid}re", w("recovery"), max(0.4, end - w("recovery")) if end else 0.9, "power1.inOut")
    if w("res_bracket") is not None:
        svg.append(_path(f"{uid}rb", _bracket_h(XD, XR, D + 30), "br"))
        _draw(cx, beat, f"#{uid}rb", w("res_bracket"), 0.45)
    if w("resilience") is not None:
        html.append(_label(cx, beat, f"{uid}rl", "resilience", (XD + XR) // 2 + 30, D + 36, w("resilience")))
        _rise(cx, beat, f"#{uid}rl", w("resilience"))
        svg.append(f'<g transform="translate({XD - 2},{D + 66})"><g id="{uid}sw" class="watch">{WATCH.format(hid=uid + "swh")}</g></g>')
        _pop(cx, beat, f"#{uid}sw", w("resilience") + 0.1)
    if w("watch") is not None:
        cx.init.append(f'gsap.set("#{uid}swh",{{rotation:0,svgOrigin:"0 2"}});')
        cx.to(f"#{uid}swh", w("watch"), {"rotation": 300}, dur=0.7, ease="power2.inOut")
        cx.event(w("watch"), "tick", "stopwatch")
    if w("return_dot") is not None:
        svg.append(f'<circle id="{uid}rd" cx="{XR}" cy="{B}" r="12" class="dot"/>')
        _pop(cx, beat, f"#{uid}rd", w("return_dot"))


def _steps_branch(cx, beat, w, uid, svg, html):
    if w("up") is not None:
        svg.append(_path(f"{uid}up", P_UP, "ln"))
        _draw(cx, beat, f"#{uid}up", w("up"), 0.7)
    if w("high") is not None:
        html.append(_label(cx, beat, f"{uid}hi", "HIGH", XE, UP - 42, w("high"), "right", "ctag"))
        _pop(cx, beat, f"#{uid}hi", w("high"))
    if w("down") is not None:
        svg.append(_path(f"{uid}lo", P_LO, "ln2"))
        _draw(cx, beat, f"#{uid}lo", w("down"), 0.7)
    if w("low") is not None:
        html.append(_label(cx, beat, f"{uid}lw", "LOW", XE, LO + 14, w("low"), "right", "ctag low"))
        _pop(cx, beat, f"#{uid}lw", w("low"))
    if w("adaptability") is not None:
        html.append(_label(cx, beat, f"{uid}al", "adaptability", XE + 30, LO + 58, w("adaptability"), "right"))
        _rise(cx, beat, f"#{uid}al", w("adaptability"))
    if w("you") is not None:
        _you(cx, beat, w, uid, svg, html)


def _you(cx, beat, w, uid, svg, html):
    """YOU? marker glides along the main line and stops at the bottom of the dip. The pill rides under the dot on the
    baseline and moves above it (inside the V) on the way down, so it never sits on a label."""
    t, t_stop = w("you"), w("you_stop")
    pts = curve_points()
    acc = _arc(pts)
    s0, stop_s = 40.0, acc[2]                         # start inside the safe zone, stop at the dip bottom
    n = 18
    frames = []
    for i in range(n + 1):
        u = i / n
        e = u * u * (3 - 2 * u)                       # ease in-out along the path
        x, y = _point_at(pts, acc, s0 + (stop_s - s0) * e)
        k = min(1.0, max(0.0, (y - B) / (D - B)))      # 0 on the baseline, 1 at the dip bottom
        frames.append((x, y, YOU_BELOW + (YOU_ABOVE - YOU_BELOW) * k, YOU_DX * k))
    dur = max(0.6, t_stop - t)
    x0, y0, o0, _ = frames[0]
    svg.append(f'<g id="{uid}yo" class="you"><g id="{uid}yi"><circle r="17" class="yd"/><circle r="6" class="ydc"/></g></g>')
    html.append(f'<div class="ypill" id="{uid}yp" style="left:{x0 - YOU_W / 2:.0f}px;top:{y0 + o0 - 22:.0f}px" '
                f'{cx.box("text", t, beat["t1"], True)}>YOU<b id="{uid}yq">?</b></div>')
    cx.init.append(f'gsap.set("#{uid}yo",{{x:{x0:.1f},y:{y0:.1f}}});')
    _pop(cx, beat, f"#{uid}yi", t)
    cx.enter(beat, f"#{uid}yp", t, {"opacity": 0}, {"opacity": 1}, dur=0.25)
    kd = ",".join(f'{{x:{x:.1f},y:{y:.1f},duration:{dur / n:.4f},ease:"none"}}' for x, y, _, _ in frames[1:])
    kp = ",".join(f'{{x:{x + dx - x0:.1f},y:{y + o - y0 - o0:.1f},duration:{dur / n:.4f},ease:"none"}}'
                  for x, y, o, dx in frames[1:])
    cx.tw.append(f'tl.to("#{uid}yo",{{keyframes:[{kd}]}},{snap(t)});')
    cx.tw.append(f'tl.to("#{uid}yp",{{keyframes:[{kp}]}},{snap(t)});')
    if w("improve") is not None:
        cx.tw.append(f'tl.fromTo("#{uid}yq",{{scale:1}},{{scale:1.45,duration:0.18,yoyo:true,repeat:1,ease:"power2.out"}},'
                     f'{snap(w("improve"))});')


def _title(cx, beat, a, uid, html):
    ti = a.get("title")
    if not ti:
        return
    t1 = cx.when(ti.get("l1_at"), beat, 0.2)
    t2 = cx.when(ti.get("l2_at"), beat, 0.6)
    tk = cx.when(ti.get("kicker_at"), beat, 4.0) if ti.get("kicker_at") is not None else None
    end = tk if tk is not None else beat["t1"]
    html.append(f'<div class="ctitle" id="{uid}tt">'
                f'<div class="ct1" id="{uid}t1" data-fit="980,40" {cx.box("text", t1, end, True)}>{esc(ti["l1"])}</div>'
                f'<div class="ct2" id="{uid}t2" data-fit="980,40" {cx.box("text", t2, end, True)}>{esc(ti["l2"])}</div></div>')
    cx.enter(beat, f"#{uid}t1", t1, {"opacity": 0, "scale": 1.3}, {"opacity": 1, "scale": 1}, dur=0.32, ease="back.out(1.5)")
    cx.event(t1, "thud", "chart title")
    _rise(cx, beat, f"#{uid}t2", t2, 22, 0.32)
    if tk is not None:
        if str(ti.get("kicker_at", "")).startswith("#"):   # on a cut: the title goes on the cut frame itself
            cx.set(f"#{uid}tt", tk, {"opacity": 0})
        else:
            cx.to(f"#{uid}tt", tk, {"opacity": 0, "y": -40, "scale": 0.8}, dur=0.24, ease="power2.in")
        html.append(f'<div class="ckick" id="{uid}kk" {cx.box("text", tk, beat["t1"], True)}>{esc(ti.get("kicker", ""))}</div>')
        cx.enter(beat, f"#{uid}kk", tk + 0.2, {"opacity": 0, "y": 10}, dur=0.3)   # after the title has left
        if ti.get("kicker_until") is not None:   # make room when the first chart label takes that row
            cx.to(f"#{uid}kk", cx.when(ti["kicker_until"], beat), {"opacity": 0}, dur=0.25)


def _slots(cx, beat, a, uid, html):
    slots = a.get("slots") or []
    if not slots:
        return
    ts = cx.when(a.get("slots_at"), beat, 0.3)
    col = cx.brand["colors"]
    times = [cx.when(s.get("at"), beat, 0) if s.get("at") is not None else None for s in slots]
    plan = []
    cols = []
    for i, s in enumerate(slots):
        x = SLOT_X0 + i * (SLOT_W + SLOT_GAP)
        sid = f"{uid}s{i}"
        cols.append(f'<div class="slot" id="{sid}" style="left:{x}px;top:{SLOT_Y}px;width:{SLOT_W}px;height:{SLOT_H}px" '
                    f'{cx.box("card", ts, beat["t1"])}><div class="sbg" id="{sid}bg"></div>'
                    f'<div class="sn" id="{sid}n"><span {cx.box("glyph", ts, beat["t1"], True)}>{i + 1}</span></div>'
                    f'<div class="sl" id="{sid}l" data-fit="{SLOT_W - 16},20" '
                    f'{cx.box("text", times[i] or beat["t1"], beat["t1"], True)}>{esc(s["label"])}</div>'
                    f'<div class="sph" id="{sid}p"></div></div>')
        if times[i] is None:
            continue
        t = times[i]
        cx.to(f"#{sid}n", t, {"backgroundColor": col["accent"], "borderColor": col["accent"], "color": col["bg"]}, dur=0.2)
        cx.to(f"#{sid}bg", t, {"opacity": 1}, dur=0.2)
        cx.to(f"#{sid}p", t, {"opacity": 0}, dur=0.15)
        cx.enter(beat, f"#{sid}l", t, {"opacity": 0, "y": 12}, dur=0.28)
        cx.event(t, "tick", f"slot {i + 1} {s['label']}")
        cs = (SLOT_W - CIRCLE) // 2
        gx, gy = x + cs + CIRCLE // 2, SLOT_Y + 4 + CIRCLE // 2      # the numeral inside the circle (qa list_rules)
        plan.append({"n": i + 1, "t_in": round(t, 3), "box": [gx - 14, gy - 17, 28, 34],
                     "row": [x, SLOT_Y, SLOT_W, SLOT_H]})
    for i, t in enumerate(times):           # the previous active slot steps back when the next is revealed
        nxt = next((u for u in times[i + 1:] if u is not None), None)
        if t is not None and nxt is not None:
            sid = f"{uid}s{i}"
            cx.to(f"#{sid}n", nxt, {"backgroundColor": col["bg"], "borderColor": col["accent"], "color": col["accent"]}, dur=0.2)
            cx.to(f"#{sid}bg", nxt, {"opacity": 0}, dur=0.2)
    cx.enter(beat, f"#{uid}sw0", ts, {"opacity": 0, "y": 16}, dur=0.32)
    html.append(f'<div id="{uid}sw0" class="slots">{"".join(cols)}</div>')
    end = getattr(cx, "segs", [{}])[-1].get("t1", 1e9)
    clear = None if beat["t1"] >= end - 0.05 else round(beat["t1"], 3)   # None: the list stays to the end of the reel
    cx.list_plan = {"items": plan, "clear_at": clear, "scaffold": True, "axis": "row",
                    "row": {"y": SLOT_Y, "w": SLOT_W, "h": SLOT_H, "gap": SLOT_GAP}}


def _ghost(cx, beat, a, uid, svg, html):
    if a.get("ghost_at") is not None:
        t = cx.when(a["ghost_at"], beat, 0.1)
        svg.append(f'<g id="{uid}gh" class="ghost">' + "".join(
            _path(f"{uid}g{i}", d, "gl") for i, d in enumerate((P_BASE, P_DESC, P_REC, P_UP, P_LO))) + "</g>")
        for i, (d0, dur) in enumerate(((0, 0.45), (0.42, 0.18), (0.58, 0.4), (0.95, 0.3), (0.95, 0.3))):
            _draw(cx, beat, f"#{uid}g{i}", t + d0, dur, "none" if i else "power1.in")
    g = a.get("ghost_from")
    if g:  # a still of the previous shot, on the first frame, shrinking away
        t0 = beat["t0"]
        sw, sh = g.get("size", [1080, 1920])
        px, py = g.get("pos", [0, 0])
        html.append(f'<div class="cghost" id="{uid}go" style="background-image:url(\'{esc(g["src"])}\');'
                    f'background-size:{sw}px {sh}px;background-position:{px}px {py}px;height:{g.get("h", 960)}px"></div>')
        cx.enter(beat, f"#{uid}go", t0, {"opacity": 1, "scale": 1}, {"opacity": 0, "scale": 0.72, "y": -60}, dur=0.42,
                 ease="power2.in")


def _unbreakable(cx, beat, a, uid, svg, html):
    """Full curve on the cut, then the tolerance line stretches right (the crash never comes) and UNBREAKABLE lands."""
    t0 = beat["t0"]
    ts = cx.when(a.get("stretch_at"), beat, 0.8)
    tw = cx.when(a.get("word_at"), beat, 2.0)
    rest = "".join(_path(f"{uid}u{i}", d, "ln" if i < 3 else "ln2", hidden=False) for i, d in enumerate((P_DESC, P_REC, P_UP, P_LO)))
    svg.append(f'<line id="{uid}ub" x1="{X0}" y1="{B}" x2="{XC}" y2="{B}" class="ln"/>'
               f'<g id="{uid}ur">{rest}<circle cx="{XC}" cy="{B}" r="15" class="dot"/></g>'
               f'<g id="{uid}ut" class="br"><line id="{uid}utl" x1="{X0}" y1="{B - 40}" x2="{XC}" y2="{B - 40}"/>'
               f'<line x1="{X0}" y1="{B - 49}" x2="{X0}" y2="{B - 31}"/>'
               f'<line id="{uid}ute" x1="{XC}" y1="{B - 49}" x2="{XC}" y2="{B - 31}"/></g>')
    html.append(_label(cx, beat, f"{uid}tl", "tolerance", (X0 + XC) // 2, B - 122, t0))
    cx.enter(beat, f"#{uid}ur", t0, {"opacity": 0.5}, {"opacity": 1}, dur=0.25)
    cx.to(f"#{uid}ur", ts, {"x": 640, "opacity": 0}, dur=0.9, ease="power2.in")
    cx.to(f"#{uid}ub", ts, {"attr": {"x2": XE}}, dur=1.0, ease="power2.inOut")
    cx.to(f"#{uid}utl", ts, {"attr": {"x2": XE}}, dur=1.0, ease="power2.inOut")
    cx.to(f"#{uid}ute", ts, {"attr": {"x1": XE, "x2": XE}}, dur=1.0, ease="power2.inOut")
    cx.to(f"#{uid}tl", ts, {"x": (XE - XC) / 2}, dur=1.0, ease="power2.inOut")
    cx.event(ts, "whoosh", "tolerance stretches")
    html.append(f'<div class="cbig" id="{uid}ww" data-fit="980,60" {cx.box("text", tw, beat["t1"], True)}>{esc(a.get("word", "UNBREAKABLE"))}</div>')
    cx.enter(beat, f"#{uid}ww", tw, {"opacity": 0, "scale": 1.4}, {"opacity": 1, "scale": 1}, dur=0.32, ease="back.out(1.6)")
    cx.event(tw, "thud", "unbreakable")
    if a.get("kicker"):
        html.append(f'<div class="ckick" id="{uid}kk" {cx.box("text", t0, beat["t1"], True)}>{esc(a["kicker"])}</div>')


def _flash(cx, beat, a, uid, html):
    """A silent inset clip that flashes in on a word for ~1 s (an image that carries a dropped line, e.g. the calm
    driver on "bounce back"). flash: {src, at, dur, media_start, box [x,y,w,h], video [left, top, width]}"""
    f = a.get("flash")
    if not f:
        return
    from ctx import floor5
    cx.check_asset(f["src"])
    t = cx.when(f.get("at"), beat, 0.5)
    dur = float(f.get("dur", 0.9))
    x, y, w, h = f.get("box", [140, 410, 800, 450])
    vl, vt, vw = f.get("video", [0, 0, w])
    fid, vid = cx.uid("fl"), cx.uid("flv")
    attrs = (f'data-start="{floor5(t)}" data-media-start="{floor5(float(f.get("media_start", 0.0)))}" '
             f'data-duration="{floor5(dur)}" data-track-index="{cx.next_track()}"')
    html.append(f'<div class="cflash" id="{fid}" data-layout-allow-overflow style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" '
                f'{cx.box("video", t, t + dur)}><video id="{vid}" src="{esc(f["src"])}" muted playsinline {attrs} '
                f'style="position:absolute;left:{vl}px;top:{vt}px;width:{vw}px"></video></div>')
    cx.init.append(f'gsap.set("#{fid}",{{autoAlpha:0}});')
    cx.enter(beat, f"#{fid}", t, {"autoAlpha": 0, "scale": 0.9}, {"autoAlpha": 1, "scale": 1}, dur=0.16, ease="power2.out")
    cx.to(f"#{fid}", t + dur - 0.16, {"autoAlpha": 0, "scale": 0.96}, dur=0.15, ease="power2.in")
    cx.event(t, "whoosh", "flash clip")


def cycle_chart(cx, beat, a):
    uid = cx.uid("cy")
    svg, html = [], []
    if a.get("mode") == "unbreakable":
        _unbreakable(cx, beat, a, uid, svg, html)
    else:
        _ghost(cx, beat, a, uid, svg, html)
        _steps(cx, beat, a, uid, svg, html)
        _title(cx, beat, a, uid, html)
        _slots(cx, beat, a, uid, html)
        _flash(cx, beat, a, uid, html)
    return (f'<div class="chart" id="{uid}"><svg class="csvg" viewBox="0 0 1080 1000" width="1080" height="1000">'
            f'{"".join(svg)}</svg>{"".join(html)}</div>')


def css(brand):
    c = brand["colors"]
    return f"""
/* cycle chart */
.chart{{position:absolute;left:0;top:0;width:1080px;height:1000px}}
.csvg{{position:absolute;left:0;top:0;overflow:visible}}
.csvg .ln{{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round;stroke-linejoin:round}}
.csvg .ln2{{fill:none;stroke:color-mix(in srgb,var(--ink) 62%,transparent);stroke-width:11;stroke-linecap:round;stroke-dasharray:none}}
.csvg path.ln2[stroke-dasharray="1"]{{stroke-dasharray:1}}
.csvg .gl{{fill:none;stroke:color-mix(in srgb,var(--ink) 22%,transparent);stroke-width:6;stroke-linecap:round;stroke-linejoin:round}}
.csvg .br,.csvg .br line{{fill:none;stroke:var(--ink);stroke-width:5;stroke-linecap:round}}
.csvg .dot{{fill:var(--accent)}}
.csvg .dotc{{fill:var(--bg)}}
.csvg .ring{{fill:none;stroke:var(--accent);stroke-width:4;opacity:0}}
.csvg .bolt path{{fill:{c['alert']}}}
.csvg .icon .ib{{fill:var(--bg);stroke:var(--accent);stroke-width:3.6;stroke-linejoin:round}}
.csvg .icon .il{{fill:none;stroke:var(--accent);stroke-width:3.6;stroke-linecap:round;stroke-linejoin:round}}
.csvg .icon .if{{fill:var(--accent);stroke:var(--accent);stroke-width:3.6}}
.csvg .watch .wf{{fill:var(--bg);stroke:var(--ink);stroke-width:4}}
.csvg .watch .wk,.csvg .watch .wh{{fill:none;stroke:var(--ink);stroke-width:4;stroke-linecap:round}}
.csvg .watch .wh{{stroke:var(--accent)}}
.csvg .you .yd{{fill:var(--ink)}}
.csvg .you .ydc{{fill:{c['highlight']}}}
.lab{{position:absolute;white-space:nowrap}}
.lab.center{{text-align:center}} .lab.right{{text-align:right}} .lab.left{{text-align:left}}
.cl{{font:italic 500 52px/1 var(--fs);color:var(--accent);white-space:nowrap}}
.ctag{{display:inline-block;font:700 28px/1 var(--fm);letter-spacing:.18em;color:var(--bg);background:var(--accent);
  padding:10px 12px 9px;border-radius:7px;white-space:nowrap}}
.ctag.low{{background:color-mix(in srgb,var(--ink) 70%,transparent)}}
.ypill{{position:absolute;width:{YOU_W}px;text-align:center;font:900 30px/1 var(--fd);
  letter-spacing:.02em;color:var(--bg);background:var(--ink);padding:7px 0 7px;border-radius:999px;white-space:nowrap}}
.ypill b{{display:inline-block;color:{c['highlight']};font-weight:900}}
.ctitle{{position:absolute;left:0;top:236px;width:1080px;transform-origin:50% 0%}}
.ct1{{position:absolute;left:0;top:0;width:1080px;height:86px;text-align:center;white-space:nowrap;
  font:900 88px/86px var(--fd);letter-spacing:-.04em;color:var(--ink);text-transform:uppercase}}
.ct2{{position:absolute;left:0;top:92px;width:1080px;text-align:center;white-space:nowrap;font:italic 400 70px/1 var(--fs);
  color:var(--accent)}}
.ckick{{position:absolute;left:0;top:232px;width:1010px;text-align:right;font:700 28px/1 var(--fm);letter-spacing:.16em;
  text-transform:uppercase;color:color-mix(in srgb,var(--ink) 72%,transparent);white-space:nowrap}}
.cbig{{position:absolute;left:0;top:520px;width:1080px;text-align:center;white-space:nowrap;font:900 132px/1 var(--fd);
  letter-spacing:-.045em;color:var(--accent);text-transform:uppercase}}
.cghost{{position:absolute;left:0;top:0;width:1080px;height:960px;background-size:1080px 1920px;background-repeat:no-repeat;
  transform-origin:50% 40%;border-radius:0;box-shadow:0 30px 80px rgba(0,0,0,.35)}}
.cflash{{position:absolute;overflow:hidden;border-radius:28px;z-index:3;background:var(--ink);
  box-shadow:0 30px 70px rgba(12,12,15,.35),0 6px 18px rgba(12,12,15,.2)}}
.slots{{position:absolute;left:0;top:0;width:1080px;height:1000px}}
.slot{{position:absolute}}
.sbg{{position:absolute;inset:0;border-radius:22px;background:color-mix(in srgb,var(--accent) 24%,var(--bg));opacity:0}}
.sn{{position:absolute;left:{(SLOT_W - CIRCLE) // 2}px;top:4px;width:{CIRCLE}px;height:{CIRCLE}px;border-radius:50%;
  border:3px solid color-mix(in srgb,var(--ink) 30%,transparent);display:flex;align-items:center;justify-content:center;
  font:900 32px/1 var(--fd);color:color-mix(in srgb,var(--ink) 66%,transparent);background:var(--bg)}}
.sl{{position:absolute;left:0;top:{CIRCLE + 10}px;width:{SLOT_W}px;text-align:center;font:800 28px/1 var(--fd);
  letter-spacing:.02em;text-transform:uppercase;color:var(--ink);white-space:nowrap}}
.sph{{position:absolute;left:44px;right:44px;top:{CIRCLE + 22}px;height:6px;border-radius:3px;
  background:color-mix(in srgb,var(--ink) 14%,transparent)}}
"""
