"""heroes_data: number and chart heroes. money-counter (the big number rolls and steps on its words, bars grow per
step, a small context line), cycle-chart (a line draws through labelled phases: plateau, cliff or dip, bottom,
recovery; a stopwatch runs, an optional slow-recovery ghost curve, a stamp) and evidence-hero (the evidence chart as
a full-panel hero: the stat slams, the chart builds, the citation card lands; extends comps_chart.py).
Every number on screen is a spoken number or a value traced from the cited figure. Reel Room's own code; the
cycle-chart is rebuilt from the Crash Out resilience chart idea.
"""
import json
import math

import comps_chart as CC
from heroes_base import (FPS, JS, Clock, Stage, box, esc, hero, make, prng, root, sfx, text_px)


def _num(v):
    s = str(v).replace(",", "")
    return float(s) if s.replace(".", "", 1).lstrip("-").isdigit() else None


def _fmt(x, dec):
    s = f"{x:,.{dec}f}"
    return s


def _shake(js, sel, t, amp=10, n=8, seed=3):
    r = prng(seed)
    for i in range(n):
        k = (1 - i / n) ** 2
        js.set(sel, {"x": round((r() - .5) * 2 * amp * k, 1), "y": round((r() - .5) * 2 * amp * k, 1)}, t + i / FPS)
    js.set(sel, {"x": 0, "y": 0}, t + n / FPS)


# ---------------------------------------------------------------------------------------------- money-counter
MN_CSS = (".rrh-money-counter .mn-kick{position:absolute;left:80px;white-space:nowrap;font-family:var(--k-fs);"
          "font-style:italic;font-weight:600;font-size:56px;line-height:1;color:var(--h-acc)}"
          ".rrh-money-counter .mn-row{position:absolute;left:70px;display:flex;align-items:baseline;gap:22px;"
          "white-space:nowrap;transform-origin:0% 80%}"
          # the padding (taken back by the margin) makes the clipping box hold the whole line box (textcheck
          # 'clip'), also when a fallback face sits the glyph box off-centre (editorial-ui clean install: 9 px
          # under at .08em); the positive top/bottom inset (9.5% of 1.14em) keeps the visible roll window as it was
          ".rrh-money-counter .mn-num{display:inline-grid;clip-path:inset(9.5% -6% 9.5% -6%);padding:.14em 0;"
          "margin:-.14em 0;"
          "font-family:var(--k-fd);font-weight:900;line-height:.86;letter-spacing:-.03em;"
          "color:var(--h-ink);font-variant-numeric:tabular-nums;white-space:nowrap}"
          ".rrh-money-counter .mn-num>span{grid-area:1/1;white-space:nowrap}"
          ".rrh-money-counter .mn-sz{visibility:hidden}"
          ".rrh-money-counter .mn-bar:last-child .mn-fill{background:repeating-linear-gradient(-45deg,var(--h-acc) 0 14px,"
          "var(--h-hl) 14px 22px)}"
          ".rrh-money-counter .mn-unit{font-family:var(--k-fd);font-weight:850;line-height:1;letter-spacing:-.01em;"
          "color:var(--h-acc);text-transform:uppercase;white-space:nowrap}"
          ".rrh-money-counter .mn-bars{position:absolute;left:80px;width:920px}"
          ".rrh-money-counter .mn-bar{position:relative;height:66px;margin-bottom:18px}"
          ".rrh-money-counter .mn-fill{position:absolute;left:0;top:0;height:66px;border-radius:12px;background:var(--h-acc);"
          "transform-origin:0 50%}"
          ".rrh-money-counter .mn-bar.cur .mn-fill{background:var(--h-hl)}"
          ".rrh-money-counter .mn-bv{position:absolute;top:10px;white-space:nowrap;font:700 32px/38px var(--h-fm);"
          "letter-spacing:.02em;color:var(--h-ink);font-size:40px;top:10px}"
          ".rrh-money-counter .mn-lab{position:absolute;left:80px;white-space:nowrap;font:700 56px/1.1 var(--k-fb);"
          "letter-spacing:-.01em;color:var(--h-ink)}")


def _mn_times(ck, steps, label, label_at):
    lands, prev = [], ck.t_in + 0.15
    for i, (_, anc) in enumerate(steps):
        t = ck.at(anc, 0.6 + 0.7 * i, "stamp", floor=prev + (0.35 if i else 0.0))
        lands.append(t)
        prev = t
    t_lab = ck.at(label_at, lands[-1] - ck.t_in + 0.3, "visual") if label else None
    return lands, t_lab


@hero("money-counter", "money_counter",
      fields={"steps": ("steps", (1, 3)), "prefix": ("text", (3, False)), "unit": ("text", (10, False)),
              "kicker": ("text", (24, False)), "label": ("text", (34, False)), "label_at": ("anchor", ()),
              "bars": ("bool", ()), "at": ("anchor", ()), "until": ("anchor", ()), "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "full-frame styles (band above the head)"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["count the money up", "roll the number", "step the number up"],
      what="the big number rolls up and slams on its word, then steps to the next number on its word ($15B to "
           "$60B), a bar grows per step, a small context line sets under it", min_secs=1.6)
def money_counter(self, steps, prefix="", unit="", kicker=None, label=None, label_at=None, bars=True, at=0.0,
                  until=None, tone="dark", layout="split", area=None, z=None):
    vals = [_num(v) for v, _ in steps]
    if not steps or any(v is None for v in vals):
        raise ValueError("money_counter: steps need numeric values, e.g. [('15', '@15'), ('60', '@60')]")
    stage = Stage(layout, area)
    ck = Clock(self, at)
    lands, t_lab = _mn_times(ck, steps, label, label_at)
    t_in = ck.t_in
    t_out = ck.end(until, max(lands[-1], t_lab or 0) + 0.7)
    dec = max((len(str(v).split(".")[1]) if "." in str(v) else 0) for v, _ in steps)
    big = f"{prefix}{_fmt(max(vals), dec)}"
    px = min(text_px(big, 940 - 0.34 * 0.62 * len(unit) * 340, 380, k=0.58, lo=120),
             int(stage.h * (0.46 if bars and len(steps) > 1 else 0.62)))
    n_b = len(steps) if bars and len(steps) > 1 else 0
    fixed = (76 if kicker else 0) + 40 + n_b * 84 + (80 if label else 0) + 20
    px = int(min(px, (stage.h - fixed) / 0.9))          # the whole stack fits the band (no clipped context line)
    upx = int(px * 0.34)
    h = (70 if kicker else 0) + px * 0.9 + 40 + n_b * 84 + (70 if label else 0)
    y = round(stage.y0 + max(10, (stage.h - h) / 2))
    pid = self.uid("mn")
    js = JS(pid)
    js.split = stage.layout == "split"
    parts, yy = [], y
    if kicker:
        parts.append(f'<div class="mn-kick" style="top:{yy}px" {box("text", t_in + 0.2, t_out)}>{esc(kicker)}</div>')
        yy += 76
    vspans = "".join(f'<span class="mn-v v{i}" id="{pid}n{i}" {box("glyph", lands[i], lands[i + 1] if i + 1 < len(vals) else t_out)}>'
                     f'{esc(prefix)}{_fmt(v if i else 0, dec)}</span>' for i, v in enumerate(vals))
    sizer = f'<span class="mn-sz">{esc(prefix)}{_fmt(max(vals), dec)}</span>'
    parts.append(f'<div class="mn-row" style="top:{yy}px"><span class="mn-num" id="{pid}n" style="font-size:{px}px">'
                 f'{sizer}{vspans}</span>'
                 + (f'<span class="mn-unit" style="font-size:{upx}px" {box("text", lands[0], t_out)}>{esc(unit)}</span>'
                    if unit else "") + "</div>")
    yy += int(px * 0.9) + 40
    if n_b:
        mx = max(vals)
        rows = "".join(f'<div class="mn-bar b{i}"><i class="mn-fill" style="width:{max(40, 760 * v / mx):.0f}px"></i>'
                       f'<span class="mn-bv" style="left:{max(40, 760 * v / mx) + 18:.0f}px" '
                       f'{box("text", lands[i] + 0.1, t_out)}>{esc(prefix)}{_fmt(v, dec)}</span></div>'
                       for i, v in enumerate(vals))
        parts.append(f'<div class="mn-bars" style="top:{yy}px">{rows}</div>')
        yy += n_b * 84
    if label:
        parts.append(f'<div class="mn-lab" style="top:{yy + 10}px" {box("text", t_lab + 0.1, t_out)}>{esc(label)}</div>')
    _mn_js(js, pid, vals, dec, prefix, lands, t_in, t_lab, t_out, n_b, bool(kicker), bool(unit),
           stage.layout == "split")
    html = root(pid, "money-counter", self, tone, "".join(parts), stage, full=stage.layout != "split",
                extra_css=MN_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "number scene")] + [sfx(t, "stamp" if i == 0 else "impact", f"number lands {i}")
                                                  for i, t in enumerate(lands)]
    ev += [sfx(t_lab, "pop", "context line", "full")] if label else []
    meta = {"times": {"in": t_in, "lands": lands, "label": t_lab, "out": t_out}, "px": px, "box": [70, y, 940, round(h)]}
    return make("money-counter", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _mn_roll(js, pid, i, a, b, t0, t1, dec, prefix):
    """Step i: the old number rolls up and out under a blur, the new one rolls up from below and lands with a small
    overshoot on its word (a slot-machine step). Step 0 counts up from 0 inside its slot first."""
    sel = f"#{pid}n{i}"
    js.hide(sel, {"yPercent": 105, "opacity": 0})
    if i == 0:
        js.set(sel, {"yPercent": 0, "opacity": 1}, t0)

        def fn(p, f):
            k = 1 - (1 - p) ** 3
            sp = 3 * (1 - p) ** 2 / max(1, (t1 - t0) * FPS)
            return {"textContent": f"{prefix}{_fmt(a + (b - a) * k, dec)}",
                    "filter": f"blur({min(5.0, sp * 60):.1f}px)" if sp * 60 > 0.6 else "none"}
        js.per_frame(sel, t0, t1, fn)
        return
    js.to(f"#{pid}n{i - 1}", {"yPercent": -105, "opacity": 0}, t1 - 0.32, 0.3, "power3.in")
    js.mblur(f"#{pid}n{i - 1}", t1 - 0.32, 0.3, dy=-200, ease_="power3.in", k=0.5)
    js.ft(sel, {"yPercent": 105, "opacity": 0}, {"yPercent": 0, "opacity": 1}, t1 - 0.14, 0.5, "back.out(1.4)")
    js.mblur(sel, t1 - 0.14, 0.36, dy=-200, ease_="expo.out", k=0.5)
    js.per_frame(sel, t1 - 0.14, t1 + 0.3,        # the digits keep rolling while the new number rises into place
                 lambda p, f: {"textContent": f"{prefix}{_fmt(a + (b - a) * (1 - (1 - p) ** 3), dec)}"})


def _mn_js(js, pid, vals, dec, prefix, lands, t_in, t_lab, t_out, n_b, kick, unit, split=True):
    js.life(t_in, t_out + 0.24)
    js.ground_in(t_in, 0.4)
    if kick:
        js.ft(".mn-kick", {"opacity": 0, "y": 30, "filter": "blur(8px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
              t_in + 0.12, 0.4, "expo.out")
    js.ft(".mn-row", {"opacity": 0, "scale": 0.9, "y": 40, "filter": "blur(12px)"},
          {"opacity": 1, "scale": 1, "y": 0, "filter": "blur(0px)"}, t_in + 0.08, 0.42, "expo.out")
    prev = 0.0
    for i, (v, t) in enumerate(zip(vals, lands)):
        r0 = max(t_in + 0.1, t - (0.75 if i == 0 else 0.45), (lands[i - 1] + 0.12) if i else 0)
        _mn_roll(js, pid, i, prev, v, r0, t, dec, prefix)
        js.ft(".mn-row", {"scale": 1.16}, {"scale": 1}, t, 0.32, "power4.out")
        _shake(js, f"#{pid}n", t + 0.3, amp=6, n=7, seed=11 + i)
        if n_b:
            js.hide(f".b{i}", {"opacity": 0})
            js.ft(f".b{i}", {"opacity": 0, "x": -30}, {"opacity": 1, "x": 0}, t - 0.05, 0.3, "expo.out")
            js.ft(f".b{i} .mn-fill", {"scaleX": 0}, {"scaleX": 1}, t - 0.05, 0.55, "expo.out")
        prev = v
    if unit:
        js.ft(".mn-unit", {"opacity": 0, "x": 40, "filter": "blur(8px)"}, {"opacity": 1, "x": 0, "filter": "blur(0px)"},
              lands[0] + 0.05, 0.36, "expo.out")
    if t_lab is not None:
        js.ft(".mn-lab", {"opacity": 0, "y": 24, "filter": "blur(6px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
              t_lab, 0.34, "expo.out")
    hold = max(lands[-1], t_lab or 0) + 0.4
    if t_out - hold > 0.3:
        js.ft(".mn-row", {"scale": 1}, {"scale": 1.03}, hold, t_out - hold, "none")
    js.to(".mn-row,.mn-kick,.mn-bars,.mn-lab", {"opacity": 0, "y": -30, "filter": "blur(8px)"}, t_out, 0.22, "power3.in")


# ---------------------------------------------------------------------------------------------- cycle-chart
CY_CSS = (".rrh-cycle-chart .cy-ttl{position:absolute;left:80px;white-space:nowrap;font:800 52px/1 var(--k-fd);"
          "letter-spacing:-.015em;color:var(--h-ink)}"
          ".rrh-cycle-chart svg.cy{position:absolute;left:0;top:0}"
          ".rrh-cycle-chart .cy-base{stroke:var(--h-sub);stroke-width:3;stroke-dasharray:10 12}"
          ".rrh-cycle-chart .cy-gl{stroke:var(--h-line);stroke-width:2}"
          ".rrh-cycle-chart .cy-ln{fill:none;stroke:var(--h-acc);stroke-width:12;stroke-linecap:round;stroke-linejoin:round}"
          ".rrh-cycle-chart .cy-gh{fill:none;stroke:var(--h-sub);stroke-width:8;stroke-linecap:round;stroke-dasharray:2 16}"
          ".rrh-cycle-chart .cy-dot{fill:var(--h-acc)}"
          ".rrh-cycle-chart .cy-lab{position:absolute;white-space:nowrap;font-family:var(--k-fs);font-style:italic;"
          "font-weight:700;font-size:46px;line-height:1.1;color:var(--h-ink);padding:0 0 8px;"
          "border-bottom:4px solid var(--h-acc)}"
          ".rrh-cycle-chart .cy-lab.last{color:var(--h-acc)}"
          ".rrh-cycle-chart .cy-w circle.f{fill:var(--h-card);stroke:var(--h-ink);stroke-width:6}"
          ".rrh-cycle-chart .cy-w path{stroke:var(--h-ink);stroke-width:6;stroke-linecap:round;fill:none}"
          ".rrh-cycle-chart .cy-w .hand{stroke:var(--h-alert);stroke-width:6}"
          ".rrh-cycle-chart .cy-stamp{position:absolute;white-space:nowrap;font:900 78px/1 var(--k-fd);letter-spacing:.03em;"
          "text-transform:uppercase;color:var(--h-g);background:var(--h-alert);border-radius:16px;padding:16px 30px;"
          "box-shadow:0 18px 40px rgba(0,0,0,.35),inset 0 0 0 5px rgba(255,255,255,.25);transform-origin:50% 50%}")
PHASES = {"drop": [0, 1], "dip": [0, 1, 2], "rise": [0, 1, 2]}
STAMP_AT = {"drop": (90, 0.5), "dip": (330, 0.06), "rise": (90, 0.04)}   # the empty quadrant of each shape   # segment ends that carry a label
SHAPES = {   # phase points as (x share, y share) of the plot box; y 0 = baseline (top), 1 = bottom
    "drop": [(0.0, 0.08), (0.42, 0.0), (0.58, 0.96), (1.0, 1.0)],
    "dip": [(0.0, 0.05), (0.24, 0.45), (0.46, 1.0), (0.82, 0.12), (1.0, 0.0)],
    "rise": [(0.0, 1.0), (0.3, 0.86), (0.64, 0.35), (1.0, 0.0)],
}


def _cy_paths(shape, g):
    x0, y0, w, h = g
    pts = [(x0 + a * w, y0 + b * h) for a, b in SHAPES[shape]]
    segs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        mx = (ax + bx) / 2
        segs.append(f"M{ax:.1f} {ay:.1f} C{mx:.1f} {ay:.1f} {mx:.1f} {by:.1f} {bx:.1f} {by:.1f}")
    return pts, segs


def _steep(shape, i):
    (ax, ay), (bx, by) = SHAPES[shape][i], SHAPES[shape][i + 1]
    return abs(by - ay) > 0.5 and abs(bx - ax) < 0.25


def _cy_times(ck, shape, labels, marks, has_stamp, stamp_at=None):
    """Segment end times + label pop times. Labels land on their words; the line draws continuously; a steep
    segment (a cliff) takes the last 0.28 s before its word and the segment before it creeps until then."""
    n_seg = len(SHAPES[shape]) - 1
    ph = PHASES[shape]
    lab_at = ph[:len(labels)] if has_stamp else ph[len(ph) - len(labels):]
    lab_t, prev = [], ck.t_in + 0.4
    for k, m in enumerate((list(marks or []) + [None] * len(labels))[:len(labels)]):
        t = ck.at(m, prev - ck.t_in + 0.6, "visual", floor=prev + 0.2)
        lab_t.append(t)
        prev = t
    ends = [None] * n_seg
    for k, si in enumerate(lab_at):
        ends[si] = lab_t[k]
    if has_stamp and stamp_at is not None and len(labels) < len(ph):
        ends[ph[len(labels)]] = ck.at(stamp_at, prev - ck.t_in + 0.8, "visual", floor=prev + 0.3)
    last = max([t for t in ends if t is not None] or [ck.t_in + 1.2])
    if ends[-1] is None:
        ends[-1] = last + 0.6
    known = [(-1, ck.t_in + 0.35)] + [(i, t) for i, t in enumerate(ends) if t is not None]
    for (i0, t0), (i1, t1) in zip(known, known[1:]):
        for j in range(i0 + 1, i1):
            ends[j] = t0 + (t1 - t0) * (j - i0) / (i1 - i0)
    for i in range(1, n_seg):
        if _steep(shape, i):
            ends[i - 1] = max(ends[i - 1] if i - 1 == 0 else ends[i - 2] + 0.12, ends[i] - 0.3)
        ends[i] = max(ends[i], ends[i - 1] + 0.12)
    starts = [ck.t_in + 0.35] + ends[:-1]
    lab_f = []
    for k, si in enumerate(lab_at):
        span = max(1e-3, ends[si] - starts[si])
        lab_f.append(min(1.0, max(0.2, (lab_t[k] - starts[si]) / span)))
    return ends, lab_at, lab_t, lab_f


def _cy_ghost(pts):
    (ax, ay), (bx, by) = pts[-3], pts[-1]
    return f"M{ax:.1f} {ay:.1f} C{ax + (bx - ax) * .6:.1f} {ay:.1f} {bx - 40:.1f} {by + (ay - by) * .55:.1f} {bx:.1f} {by + (ay - by) * .35:.1f}"


WATCH = ('<g class="cy-w"><circle class="f" cx="0" cy="0" r="54"/><path d="M-10 -66 H10 M0 -66 V-54"/>'
         '<path d="M0 -42 V-34 M42 0 H34 M0 42 V34 M-42 0 H-34"/><path class="hand" d="M0 6 V-40"/></g>')


@hero("cycle-chart", "cycle_chart",
      fields={"shape": ("enum", (("drop", "dip", "rise"),)), "labels": ("texts", (0, 3, 18)),
              "marks": ("anchors", (3,)), "title": ("text", (28, False)), "title_at": ("anchor", ()), "stopwatch": ("bool", ()),
              "ghost": ("bool", ()), "stamp": ("text", (14, False)), "stamp_at": ("anchor", ()),
              "at": ("anchor", ()), "until": ("anchor", ()), "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)"], layouts=["split", "card", "stage"],
      say=["draw the drop", "show the crash and recovery", "chart the cycle"],
      what="a line draws through labelled phases on their words (plateau then a cliff, or dip, bottom and recovery), a "
           "stopwatch runs, an optional slow-recovery ghost curve, and a stamp slams on the payoff word", min_secs=2.4)
def cycle_chart(self, shape, labels=None, marks=None, title=None, stopwatch=False, ghost=False, stamp=None, stamp_at=None,
                at=0.0, title_at=None, until=None, tone="dark", layout="split", area=None, z=None):
    if shape not in SHAPES:
        raise ValueError(f"cycle_chart: shape must be one of {sorted(SHAPES)}")
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    labels = list(labels or [])[:len(PHASES[shape])]
    ends, lab_at, lab_t, lab_f = _cy_times(ck, shape, labels, marks, bool(stamp), stamp_at)
    t_st = ck.at(stamp_at, ends[-1] - t_in + 0.2, "stamp", floor=max(lab_t or [t_in]) + 0.2) if stamp else None
    t_out = ck.end(until, max(ends[-1], t_st or 0) + 0.8)
    pid = self.uid("cy")
    js = JS(pid)
    js.split = stage.layout == "split"
    top = stage.y0 + (90 if title else 30)
    g = (110, top + 150, 860, stage.y1 - top - 250)
    pts, segs = _cy_paths(shape, g)
    bot = g[1] + g[3] + 30
    full = segs[0] + "".join(" " + d[d.index("C"):] for d in segs[1:])
    area = f'{full} L{pts[-1][0]:.1f} {bot} L{pts[0][0]:.1f} {bot} Z'
    svg = [f'<defs><clipPath id="{pid}ac"><rect class="cy-acr" x="{g[0]}" y="0" width="0" height="1920"/></clipPath>'
           f'<linearGradient id="{pid}ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--h-acc)" '
           f'stop-opacity=".34"/><stop offset="1" stop-color="var(--h-acc)" stop-opacity="0"/></linearGradient></defs>',
           f'<path class="cy-area" d="{area}" fill="url(#{pid}ag)" clip-path="url(#{pid}ac)"/>',
           f'<line class="cy-base" x1="{g[0]}" y1="{g[1]}" x2="{g[0] + g[2]}" y2="{g[1]}"/>']
    svg += [f'<line class="cy-gl" x1="{g[0]}" y1="{g[1] + g[3] * k / 4:.0f}" x2="{g[0] + g[2]}" y2="{g[1] + g[3] * k / 4:.0f}"/>'
            for k in range(1, 5)]
    svg += [f'<line class="cy-gl" x1="{g[0] + g[2] * k / 6:.0f}" y1="{g[1] + g[3] + 6}" x2="{g[0] + g[2] * k / 6:.0f}" '
            f'y2="{g[1] + g[3] + 20}"/>' for k in range(7)]
    if ghost and shape == "dip":
        svg.append(f'<path class="cy-gh" d="{_cy_ghost(pts)}" pathLength="1"/>')
    svg += [f'<path class="cy-ln s{i}" d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>'
            for i, d in enumerate(segs)]
    svg.append(f'<g class="cy-dg"><circle class="cy-dot" r="18" cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}"/></g>')
    if stopwatch:
        svg.append(f'<g transform="translate(930 {stage.y0 + 80}) scale(1.05)">{WATCH}</g>')
    html = [f'<div class="cy-ttl" style="top:{stage.y0 + 20}px" {box("text", t_in + 0.2, t_out)}>{esc(title)}</div>'
            if title else "", f'<svg class="cy" width="1080" height="1920">{"".join(svg)}</svg>']
    for k, (lab, si) in enumerate(zip(labels, lab_at)):
        (ax, ay), (bx, by) = pts[si], pts[si + 1]
        x, y = ax + (bx - ax) * lab_f[k], ay + (by - ay) * lab_f[k]
        last = k == len(labels) - 1
        lx = min(max(70, x - 40 * len(lab) * 0.5), 1000 - 21 * len(lab) - 40)
        ly = y + 40 if y < g[1] + g[3] * 0.5 else y - 96
        html.append(f'<div class="cy-lab l{k}{" last" if last else ""}" style="left:{lx:.0f}px;top:{ly:.0f}px" '
                    f'{box("text", lab_t[k] + 0.1, t_out)}>{esc(lab)}</div>')
    if stamp:
        sx, sy = STAMP_AT[shape]
        html.append(f'<div class="cy-stamp" style="left:{sx}px;top:{g[1] + g[3] * sy:.0f}px;font-size:'
                    f'{min(64, int(330 / (0.62 * max(4, len(stamp)))))}px" {box("text", t_st + 0.1, t_out)}>{esc(stamp)}</div>')
    t_ttl = min(ck.early(title_at, 0.1), ends[-1] - 0.3) if title else None
    _cy_js(js, pid, pts, ends, lab_t, t_in, t_st, t_out, stopwatch, ghost and shape == "dip", t_ttl)
    out = root(pid, "cycle-chart", self, tone, "".join(html) + js.svg_defs(), stage, extra_css=CY_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "chart"), sfx(t_in + 0.3, "whoosh", "line draws", "full")]
    ev += [sfx(t, "pop", f"phase {k}") for k, t in enumerate(lab_t)]
    ev += [sfx(t_st, "stamp", "stamp")] if t_st else []
    meta = {"times": {"in": t_in, "ends": ends, "stamp": t_st, "out": t_out}, "box": [70, stage.y0, 940, stage.h]}
    return make("cycle-chart", self, pid, out, js, ev, t_in, t_out + 0.25, meta)


def _cy_js(js, pid, pts, ends, lab_t, t_in, t_st, t_out, stopwatch, ghost, t_ttl=None):
    js.life(t_in, t_out + 0.24)
    js.ground_in(t_in, 0.4)
    if t_ttl is not None:
        js.ft(".cy-ttl", {"opacity": 0, "y": 30, "filter": "blur(8px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
              max(t_in + 0.1, t_ttl), 0.4, "expo.out")
    js.ft(".cy-base", {"opacity": 0, "scaleX": 0.6}, {"opacity": 1, "scaleX": 1}, t_in + 0.1, 0.5, "expo.out")
    js.hide(".cy-dg", {"opacity": 0})
    js.set(".cy-dg", {"opacity": 1}, t_in + 0.3)
    start = t_in + 0.3
    for i, t in enumerate(ends):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        steep = abs(by - ay) > 200 and abs(bx - ax) < 220
        s0 = max(start, t - 0.28) if steep else start
        ez = "power3.in" if steep else ("none" if t - s0 > 1.5 else "sine.inOut")   # a long creep never stalls
        js.ft(f".s{i}", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, s0, t - s0, ez)
        js.to(".cy-acr", {"attr": {"width": round(bx - pts[0][0], 1)}}, s0, t - s0, ez)
        js.to(".cy-dot", {"attr": {"cx": round(bx, 1), "cy": round(by, 1)}}, s0, t - s0, ez)
        if steep:
            js.mblur(".cy-dg", s0, t - s0, dx=bx - ax, dy=by - ay, ease_="power3.in", k=0.6)
            _shake(js, ".cy", t, amp=9, n=8, seed=5)
        start = t
    for k, t in enumerate(lab_t):
        js.hide(f".l{k}", {"opacity": 0})
        js.ft(f".l{k}", {"opacity": 0, "scale": 0.6, "y": 20, "filter": "blur(6px)"},
              {"opacity": 1, "scale": 1, "y": 0, "filter": "blur(0px)"}, t + 0.02, 0.34, "back.out(2.2)")
    if ghost:
        js.hide(".cy-gh", {"opacity": 0})
        js.ft(".cy-gh", {"opacity": 0}, {"opacity": 0.7}, ends[-3] + 0.1, 0.5, "power2.out")
    if stopwatch:
        js.ft(".cy-w", {"opacity": 0, "scale": 0.5}, {"opacity": 1, "scale": 1}, t_in + 0.2, 0.34, "back.out(2.2)")
        js.hide(".cy-w .hand", {"rotation": 0, "svgOrigin": "0 6"})
        js.to(".cy-w .hand", {"rotation": 360 * max(1, round(ends[-1] - t_in))}, t_in + 0.3, ends[-1] - t_in - 0.3, "none")
    if t_st:
        js.hide(".cy-stamp", {"opacity": 0})
        js.ft(".cy-stamp", {"opacity": 0, "scale": 1.7, "rotation": -18, "filter": "blur(8px)"},
              {"opacity": 1, "scale": 1, "rotation": -8, "filter": "blur(0px)"}, t_st, 0.26, "power4.out")
    js.to(".cy,.cy-lab,.cy-ttl,.cy-stamp", {"opacity": 0, "y": -26, "filter": "blur(8px)"}, t_out, 0.22, "power3.in")


# ---------------------------------------------------------------------------------------------- evidence-hero
EH_CSS = (".rrh-evidence-hero .eh-kick{position:absolute;left:80px;white-space:nowrap;font:600 24px/1 var(--h-fm);"
          "letter-spacing:.16em;text-transform:uppercase;color:var(--h-sub)}"
          ".rrh-evidence-hero .eh-stat{position:absolute;left:70px;display:flex;align-items:flex-end;gap:26px;white-space:nowrap}"
          ".rrh-evidence-hero .eh-num{display:inline-block;font:900 190px/.84 var(--k-fd);letter-spacing:-.03em;"
          "color:var(--h-acc);transform-origin:0% 100%}"
          ".rrh-evidence-hero .eh-lab{display:inline-block;font-family:var(--k-fs);font-style:italic;font-weight:600;"
          "font-size:46px;line-height:1.05;color:var(--h-ink);padding-bottom:12px;white-space:nowrap}"
          ".rrh-evidence-hero .eh-leg{position:absolute;left:80px;display:flex;gap:30px;white-space:nowrap;"
          "font:700 30px/1.2 var(--k-fb);color:var(--h-ink)}"
          ".rrh-evidence-hero .eh-leg span{display:inline-flex;align-items:center;gap:10px}"
          ".rrh-evidence-hero .eh-leg i{width:22px;height:22px;border-radius:6px;display:inline-block}"
          ".rrh-evidence-hero svg.eh{position:absolute;left:0;top:0}"
          ".rrh-evidence-hero .ec-ax{font:600 30px var(--k-fb);fill:var(--h-ink);opacity:.7}"
          ".rrh-evidence-hero .ec-axl{font:600 20px var(--k-fb);letter-spacing:.14em;fill:var(--h-sub)}"
          ".rrh-evidence-hero .ec-grid{stroke:var(--h-line);stroke-width:2}"
          ".rrh-evidence-hero .eh-src{position:absolute;right:70px;display:flex;gap:14px;align-items:center;white-space:nowrap;"
          "padding:16px 22px;border-radius:16px;background:var(--h-card);box-shadow:var(--h-shadow);"
          "font:600 28px/1.2 var(--k-fb);color:var(--h-ink);transform-origin:100% 100%}"
          ".rrh-evidence-hero .eh-src b{font:700 18px/1 var(--h-fm);letter-spacing:.14em;padding:7px 10px;border-radius:6px;"
          "background:var(--h-acc);color:var(--h-g)}")


@hero("evidence-hero", "evidence_hero",
      fields={"kind": ("enum", (("line", "bar"),)), "citation": ("source", (60,)), "series": ("series", (1, 3)),
              "labels": ("texts", (2, 6, 8)), "stat": ("text", (8, False)), "stat_label": ("text", (30, False)),
              "kicker": ("text", (30, False)), "highlight": ("pair", ()), "at": ("anchor", ()),
              "draw": ("anchor", ()), "stamp": ("anchor", ()), "highlight_at": ("anchor", ()),
              "until": ("anchor", ()), "y_max": ("num", (1, 1e9)), "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "full-frame styles (stage takeover)"],
      layouts=["split", "card", "stage", "media"], needs=["sources"],
      say=["slam the stat and show the study", "evidence hero", "the study chart, big"],
      what="the study's key number slams in, the chart rebuilt from the cited figure builds on your words, the "
           "citation card lands; one bar can ring while the rest dim", min_secs=2.4)
def evidence_hero(self, kind, citation, series, labels, stat=None, stat_label=None, kicker=None, highlight=None,
                  at=0.0, draw=None, stamp=None, highlight_at=None, until=None, y_max=None, y_label=None,
                  tone="cream", layout="split", area=None, z=None):
    CC._check(kind, citation, series, labels)
    stage = Stage(layout, area)
    times = CC._times(self, at, draw, stamp, highlight_at, until, stat, highlight)
    t_in, t_draw, t_st, t_hl, t_out = times
    pid = self.uid("eh")
    js = JS(pid)
    js.split = stage.layout == "split"
    colors = CC._colors(self, series)
    ymax = float(y_max or max(max(s["values"]) for s in series) * 1.1 or 1)
    y = stage.y0 + 10
    parts = []
    if kicker:
        parts.append(f'<div class="eh-kick" style="top:{y}px" {box("text", t_in + 0.1, t_out)}>{esc(kicker)}</div>')
        y += 46
    if stat:
        parts.append(f'<div class="eh-stat" style="top:{y}px"><span class="eh-num" {box("glyph", t_st, t_out)}>'
                     f'{esc(stat)}</span>' + (f'<span class="eh-lab" {box("text", t_st + 0.1, t_out)}>{esc(stat_label)}'
                                              f'</span>' if stat_label else "") + "</div>")
        y += 180
    legend = "".join(f'<span><i style="background:{c}"></i>{esc(s["name"])}</span>' for s, c in zip(series, colors))
    parts.append(f'<div class="eh-leg" style="top:{y + 6}px">{legend}</div>')
    g = (150, y + 70, 820, stage.y1 - y - 70 - 175)
    marks, centers = (CC._line_svg(g, labels, series, colors, ymax) if kind == "line"
                      else CC._bar_svg(g, labels, series, colors, ymax, highlight))
    svg = "".join(CC._axes(g, labels, ymax, y_label, None, centers) + marks)
    parts.append(f'<svg class="eh" width="1080" height="1920">{svg}</svg>')
    parts.append(f'<div class="eh-src" style="top:{stage.y1 - 76}px"><b>SOURCE</b><span {box("text", t_draw, t_out)}>'
                 f'{esc(citation)}</span></div>')
    _eh_js(js, pid, kind, len(labels), times, highlight)
    html = root(pid, "evidence-hero", self, tone, "".join(parts), stage, full=stage.layout != "split",
                extra_css=EH_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "evidence"), sfx(t_in + 0.3, "whoosh", "chart builds", "full"),
          sfx(t_draw, "pop", "citation lands")]
    ev += [sfx(t_st, "stamp", f"{stat} slam")] if t_st is not None else []
    ev += [sfx(t_hl, "click", "highlight")] if t_hl is not None else []
    meta = {"times": dict(zip(("in", "draw", "stamp", "highlight", "out"), times)), "citation": citation,
            "box": [70, stage.y0, 940, stage.h]}
    return make("evidence-hero", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _eh_js(js, pid, kind, n, times, highlight):
    t_in, t_draw, t_st, t_hl, t_out = times
    js.life(t_in, t_out + 0.24)
    js.ground_in(t_in, 0.4)
    js.ft(".eh-kick,.eh-leg", {"opacity": 0, "y": 24, "filter": "blur(6px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
          t_in + 0.12, 0.4, "expo.out")
    js.ft("svg.eh", {"opacity": 0, "y": 40}, {"opacity": 1, "y": 0}, t_in + 0.15, 0.45, "expo.out")
    span = max(0.3, t_draw - t_in - 0.3)
    if kind == "line":
        js.ft(".ec-ln", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t_in + 0.3, round(span, 3), "power2.inOut")
        for j in range(n):
            js.ft(f".ec-m{j}", {"scale": 0, "transformOrigin": "50% 50%"}, {"scale": 1}, t_in + 0.3 + span * j / max(1, n - 1),
                  0.25, "back.out(2.2)")
    else:
        for gi in range(n):
            js.ft(f".ec-g{gi}", {"scaleY": 0, "transformOrigin": "50% 100%"}, {"scaleY": 1}, t_in + 0.3 + span * gi / n,
                  0.45, "power4.out")
    js.hide(".eh-src", {"opacity": 0})
    js.ft(".eh-src", {"opacity": 0, "y": 60, "rotation": 6, "scale": 0.9, "filter": "blur(8px)"},
          {"opacity": 1, "y": 0, "rotation": -1.5, "scale": 1, "filter": "blur(0px)"}, t_draw, 0.42, "back.out(1.4)")
    if t_st is not None:
        js.hide(".eh-num,.eh-lab", {"opacity": 0})
        js.ft(".eh-num", {"opacity": 0, "scale": 1.7, "filter": "blur(14px)"}, {"opacity": 1, "scale": 1, "filter": "blur(0px)"},
              t_st, 0.26, "power4.out")
        _shake(js, ".eh-stat", t_st + 0.2, amp=8, n=8, seed=7)
        js.ft(".eh-lab", {"opacity": 0, "x": 50}, {"opacity": 1, "x": 0}, t_st + 0.13, 0.34, "expo.out")
    if t_hl is not None:
        js.ft(".ec-ring", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t_hl, 0.5, "power2.inOut")
        js.lines.append(f"tl.to({json.dumps(f'#{pid} .ec-bar:not(.ec-b{highlight[0]}-{highlight[1]})')},"
                        f"{{opacity:.35,duration:.3,ease:'power2.out'}},{CC.q(t_hl)});")
    js.to(".eh-stat,.eh-leg,svg.eh,.eh-src,.eh-kick", {"opacity": 0, "y": -26, "filter": "blur(8px)"}, t_out, 0.22,
          "power3.in")
