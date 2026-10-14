"""comps_chart: the evidence-chart kit piece ("show the study"): a line or bar chart rebuilt from a cited figure, with
the big takeaway number stamped on its word and the citation always on the card.

    p = k.evidence_chart(kind="line", citation="Chaumont et al., Sci Rep 2018",
                         labels=["BSL", "1", "2", "3"], series=[{"name": "sham vape", "values": [0, 140, 315, 345]},
                                                               {"name": "nicotine vape", "values": [0, 90, 243, 287]}],
                         stat="33%", stat_label="less blood-vessel dilation", kicker="RANDOMIZED TRIAL · HUMANS",
                         at="@vaping", draw="@flow", stamp="@clamps", y_max=400, y_label="PERFUSION UNIT")
    p = k.evidence_chart(kind="bar", citation="Lei et al., Sci Rep 2017", labels=["0 h", "24 h", "48 h", "72 h"],
                         series=[{"name": "Control", "values": [100, 66, 34, 8]},
                                 {"name": "Nicotine", "values": [100, 82, 57, 56]}],
                         highlight=[3, 1], highlight_at="@longer", title="72 hrs later the wound was still half open")

Rules (same as inserts.md "nothing decorative over a claim"): every number on the card comes from the speaker or the
cited figure; `citation` is required and always shown; values are traced from the figure, never invented. The last
series is the "effect" series (accent colour); the others step down from ink. Seek-safe like every kit piece: hidden
states set once at build, entrances are fromTo(immediateRender:false) on quantised frames, no randomness.
Built from the showcase showcase vaping charts (Chaumont 2018 line chart, Lei 2017 bar chart with the highlighted bar).
Registered into rrkit by register(Kit, COMPONENTS); Reel Room's own code.
"""
import json

from rrkit_base import Piece, box, esc, mix, place, q, sfx

MARKERS = ("circle", "square", "triangle")
CSS = """<style data-rrk-chart>
.rrk-evidence-chart{position:absolute;font-family:var(--k-fb);color:var(--k-on)}
.rrk-evidence-chart .ec-card{position:absolute;inset:0;border-radius:40px;background:var(--k-surf);box-shadow:var(--k-shadow)}
.rrk-evidence-chart .ec-kick{position:absolute;left:48px;top:40px;font:600 24px/1 var(--k-fb);letter-spacing:.16em;color:var(--k-sub)}
.rrk-evidence-chart .ec-stat{position:absolute;left:48px;display:flex;align-items:flex-end;gap:22px}
.rrk-evidence-chart .ec-num{font:800 150px/.86 var(--k-fd);letter-spacing:-.03em;color:var(--k-acc);display:inline-block}
.rrk-evidence-chart .ec-lab{font:italic 500 40px/1.12 var(--k-fs);max-width:520px;padding-bottom:10px;display:inline-block}
.rrk-evidence-chart .ec-title{position:absolute;left:48px;right:48px;font:700 46px/1.14 var(--k-fd);letter-spacing:-.01em}
.rrk-evidence-chart .ec-leg{position:absolute;left:48px;right:48px;display:flex;flex-wrap:wrap;gap:10px 26px;font:500 26px/1.2 var(--k-fb)}
.rrk-evidence-chart .ec-leg span{display:inline-flex;align-items:center;gap:10px}
.rrk-evidence-chart .ec-leg i{width:22px;height:22px;border-radius:6px;display:inline-block}
.rrk-evidence-chart svg{position:absolute;left:0;top:0}
.rrk-evidence-chart .ec-ax{font:500 24px var(--k-fb);fill:var(--k-sub)}
.rrk-evidence-chart .ec-axl{font:600 20px var(--k-fb);letter-spacing:.14em;fill:var(--k-sub)}
.rrk-evidence-chart .ec-grid{stroke:var(--k-line);stroke-width:2}
.rrk-evidence-chart .ec-src{position:absolute;left:48px;right:48px;bottom:34px;display:flex;gap:14px;align-items:center;font:500 22px/1.25 var(--k-fb);color:var(--k-sub)}
.rrk-evidence-chart .ec-src b{font:700 17px/1 var(--k-fb);letter-spacing:.14em;padding:6px 9px;border-radius:6px;background:var(--k-faint);color:var(--k-on)}
</style>"""


def _colors(kit, series):
    ink, acc = kit.brand["colors"]["ink"], kit.brand["colors"]["accent"]
    n = len(series)
    return [s.get("color") and kit.color(s["color"]) or (acc if i == n - 1 else mix(ink, kit.brand["colors"]["bg"], 0.85 - 0.5 * i / max(1, n - 1)))
            for i, s in enumerate(series)]


def _check(kind, citation, series, labels):
    if kind not in ("line", "bar"):
        raise ValueError("evidence_chart: kind must be 'line' or 'bar'")
    if not str(citation or "").strip():
        raise ValueError("evidence_chart: citation is required (every number on screen needs its source)")
    if not series or any(len(s.get("values", [])) != len(labels or []) for s in series):
        raise ValueError("evidence_chart: every series needs one value per label")


def _marker(kind, x, y, cls, color):
    if kind == "square":
        return f'<rect x="{x - 8:.1f}" y="{y - 8:.1f}" width="16" height="16" class="{cls}" fill="{color}"/>'
    if kind == "triangle":
        return f'<path d="M{x:.1f} {y - 11:.1f}L{x + 10:.1f} {y + 8:.1f}L{x - 10:.1f} {y + 8:.1f}Z" class="{cls}" fill="{color}"/>'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="{cls}" fill="{color}"/>'


def _axes(g, labels, y_max, y_label, x_label, centers):
    x0, y0, pw, ph = g
    out = []
    for k in range(5):
        v = y_max * k / 4
        yy = y0 + ph - ph * k / 4
        out.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x0 + pw}" y2="{yy:.1f}" class="ec-grid"/>'
                   f'<text x="{x0 - 16}" y="{yy + 8:.1f}" class="ec-ax" text-anchor="end">{v:g}</text>')
    for lab, cx in zip(labels, centers):
        out.append(f'<text x="{cx:.1f}" y="{y0 + ph + 38}" class="ec-ax" text-anchor="middle">{esc(lab)}</text>')
    if y_label:
        out.append(f'<text x="22" y="{y0 + ph / 2:.1f}" class="ec-axl" text-anchor="middle" '
                   f'transform="rotate(-90 22 {y0 + ph / 2:.1f})">{esc(y_label)}</text>')
    if x_label:
        out.append(f'<text x="{x0 + pw / 2:.1f}" y="{y0 + ph + 76}" class="ec-axl" text-anchor="middle">{esc(x_label)}</text>')
    return out


def _line_svg(g, labels, series, colors, y_max):
    x0, y0, pw, ph = g
    step = pw / max(1, len(labels) - 1)
    centers = [x0 + i * step for i in range(len(labels))]
    out = []
    for si, (s, c) in enumerate(zip(series, colors)):
        pts = [(centers[i], y0 + ph - min(v, y_max) / y_max * ph) for i, v in enumerate(s["values"])]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        out.append(f'<path d="{d}" class="ec-ln" pathLength="1" fill="none" stroke="{c}" stroke-width="6" '
                   f'stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="1"/>')
        mk = s.get("marker") or MARKERS[si % len(MARKERS)]
        out += [_marker(mk, x, y, f"ec-mk ec-m{j}", c) for j, (x, y) in enumerate(pts)]
    return out, centers


def _bar_svg(g, labels, series, colors, y_max, highlight):
    x0, y0, pw, ph = g
    gw = pw / len(labels)
    bw = min(56, gw * 0.8 / len(series))
    centers, out, ring = [], [], ""
    for gi in range(len(labels)):
        cx = x0 + gw * (gi + 0.5)
        centers.append(cx)
        for si, (s, c) in enumerate(zip(series, colors)):
            v = s["values"][gi]
            bh = min(v, y_max) / y_max * ph
            bx = cx - bw * len(series) / 2 + si * bw
            out.append(f'<rect x="{bx:.1f}" y="{y0 + ph - bh:.1f}" width="{bw - 4:.1f}" height="{max(bh, 0.5):.1f}" rx="4" '
                       f'fill="{c}" class="ec-bar ec-g{gi} ec-b{gi}-{si}"/>')
            if highlight and [gi, si] == list(highlight):
                ring = (f'<rect x="{bx - 10:.1f}" y="{y0 + ph - bh - 12:.1f}" width="{bw + 16:.1f}" height="{bh + 18:.1f}" '
                        f'rx="12" fill="none" stroke="var(--k-alert)" stroke-width="5" pathLength="1" stroke-dasharray="1" '
                        f'class="ec-ring"/>')
    return out + ([ring] if ring else []), centers


def _layout(h, stat, title, n_series):
    """vertical rhythm inside the card -> (top of stat, top of title, top of legend, plot box y0, plot height)"""
    y = 96
    ys = y if stat else None
    y += 150 if stat else 0
    yt = y + 14 if title else None
    y += 130 if title else 10
    yl = y + 10
    y += 40 * ((n_series + 1) // 2) + 50
    return ys, yt, yl, y, h - y - 200


def _times(self, at, draw, stamp, highlight_at, until, stat, highlight):
    t_in = self.cursor()(at, 0.0, "visual")
    one = lambda: self.cursor(start=t_in)  # noqa: E731  draw, stamp and highlight each search from the entrance
    t_draw = max(one()(draw, 1.6, "none", rel=t_in), t_in + 0.8)
    t_stamp = max(one()(stamp, 0.4, "stamp", rel=t_draw), t_in + 0.35) if stat else None
    last = max(t_stamp or 0, t_draw)
    t_hl = max(one()(highlight_at, 0.5, "visual", rel=last), t_draw) if highlight else None
    t_out = self.until(until, t_in, max(t_hl or 0, last) + 1.6 - t_in, one())
    return t_in, t_draw, t_stamp, t_hl, t_out


def _html(pid, kit, theme, geo, parts, t_in, t_out):
    px, py, w, h = geo
    kicker, stat, stat_label, title, legend, svg, citation, ys, yt, yl = parts
    b = lambda kind: box(kind, t_in, t_out)  # noqa: E731
    inner = f'<div class="ec-card" {box("card", t_in, t_out, False)}></div>'
    if kicker:
        inner += f'<div class="ec-kick" {b("text")}>{esc(kicker)}</div>'
    if stat:
        inner += (f'<div class="ec-stat" style="top:{ys}px"><span class="ec-num" {b("glyph")}>{esc(stat)}</span>'
                  + (f'<span class="ec-lab" {b("text")}>{esc(stat_label)}</span>' if stat_label else "") + "</div>")
    if title:
        inner += f'<div class="ec-title" style="top:{yt}px" {b("text")}>{esc(title)}</div>'
    inner += f'<div class="ec-leg" style="top:{yl}px">{legend}</div>'
    inner += f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{svg}</svg>'
    inner += f'<div class="ec-src"><b>SOURCE</b><span {b("text")}>{esc(citation)}</span></div>'
    return (CSS + f'<div class="rrk rrk-evidence-chart" id="{pid}" data-layout-allow-overflow style="left:{px}px;top:{py}px;'
            f'width:{w}px;height:{h}px;{kit.vars(theme)}">{inner}</div>')


def _js(pid, kind, n_points, times, highlight):
    t_in, t_draw, t_stamp, t_hl, t_out = times
    s = json.dumps("#" + pid)
    J = []

    def tw(sel, frm, to, t, dur, ease):
        sel = json.dumps(f"#{pid} {sel}" if sel else "#" + pid)
        J.append(f"gsap.set({sel},{json.dumps(frm)});tl.fromTo({sel},{json.dumps(frm)},"
                 f"Object.assign({json.dumps(to)},{{duration:{dur},ease:'{ease}',immediateRender:false}}),{q(t)});")
    tw("", {"opacity": 0, "y": 40, "filter": "blur(10px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"}, t_in, 0.5, "expo.out")
    span = max(0.3, t_draw - t_in - 0.3)
    if kind == "line":
        tw(".ec-ln", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t_in + 0.3, round(span, 3), "power1.inOut")
        for j in range(n_points):
            tw(f".ec-m{j}", {"scale": 0, "transformOrigin": "50% 50%"}, {"scale": 1},
               t_in + 0.3 + span * j / max(1, n_points - 1), 0.25, "back.out(2.2)")
    else:
        for gi in range(n_points):
            tw(f".ec-g{gi}", {"scaleY": 0, "transformOrigin": "50% 100%"}, {"scaleY": 1},
               t_in + 0.3 + span * gi / max(1, n_points), 0.45, "power4.out")
    if t_stamp is not None:
        tw(".ec-num", {"scale": 1.45, "opacity": 0, "filter": "blur(12px)", "transformOrigin": "0% 100%"},
           {"scale": 1, "opacity": 1, "filter": "blur(0px)"}, t_stamp, 0.27, "power4.out")
        tw(".ec-lab", {"x": 50, "opacity": 0}, {"x": 0, "opacity": 1}, t_stamp + 0.13, 0.33, "expo.out")
    if t_hl is not None:
        tw(".ec-ring", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t_hl, 0.5, "power2.inOut")
        sel = json.dumps(f"#{pid} .ec-bar:not(.ec-b{highlight[0]}-{highlight[1]})")
        J.append(f"tl.to({sel},{{opacity:.38,duration:.3,ease:'power2.out'}},{q(t_hl)});")
    J.append(f"tl.to({s},{{opacity:0,filter:'blur(8px)',duration:.3,ease:'power3.in'}},{q(t_out)});")
    return J


def evidence_chart(self, kind, citation, series, labels, at=0.0, until=None, draw=None, stat=None, stat_label=None,
                   stamp=None, kicker=None, title=None, highlight=None, highlight_at=None, y_max=None, y_label=None,
                   x_label=None, pos="center", x=None, y=None, w=980, h=None, theme="light"):
    """A cited line or bar chart builds on the words; `stat` stamps on `stamp`; `highlight` = [group, series] rings
    one bar on `highlight_at` and dims the rest. See the module docstring."""
    _check(kind, citation, series, labels)
    times = _times(self, at, draw, stamp, highlight_at, until, stat, highlight)
    h = h or (1120 if stat or title else 980)
    px, py = place(pos, w, h, x, y)
    pid = self.uid("ec")
    colors = _colors(self, series)
    ymax = float(y_max or max(max(s["values"]) for s in series) * 1.1 or 1)
    ys, yt, yl, gy, gh = _layout(h, stat, title, len(series))
    g = (140, gy, w - 200, gh)
    if kind == "line":
        marks, centers = _line_svg(g, labels, series, colors, ymax)
    else:
        marks, centers = _bar_svg(g, labels, series, colors, ymax, highlight)
    svg = "".join(_axes(g, labels, ymax, y_label, x_label, centers) + marks)
    legend = "".join(f'<span><i style="background:{c}"></i>{esc(s["name"])}</span>' for s, c in zip(series, colors))
    parts = (kicker, stat, stat_label, title, legend, svg, citation, ys, yt, yl)
    html = _html(pid, self, theme, (px, py, w, h), parts, times[0], times[4])
    t_in, t_draw, t_stamp, t_hl, t_out = times
    ev = [sfx(t_in, "pop", "chart card"), sfx(t_in + 0.3, "whoosh", "chart draws", "full")]
    ev += [sfx(t_stamp, "stamp", f"{stat} stamp")] if t_stamp is not None else []
    ev += [sfx(t_hl, "click", "highlight")] if t_hl is not None else []
    js = _js(pid, kind, len(labels), times, highlight)
    meta = {"times": dict(zip(("in", "draw", "stamp", "highlight", "out"), times)), "box": [px, py, w, h],
            "citation": citation}
    return Piece("evidence-chart", pid, html, js, sorted(ev, key=lambda e: e["t"]), t_in, t_out + 0.3, meta)


def register(Kit, COMPONENTS):
    """Attach the piece to the Kit and the planner registry (rrkit calls this once)."""
    Kit.evidence_chart = evidence_chart
    COMPONENTS["evidence-chart"] = {
        "method": "evidence_chart", "say": ["show the study", "chart the numbers", "show the graph from the paper"],
        "what": "a line or bar chart rebuilt from the cited figure draws on your words, the key number stamps, the "
                "citation stays on the card"}
