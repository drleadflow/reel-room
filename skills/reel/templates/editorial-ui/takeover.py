"""Editorial UI "takeover" scene (Motion v2): the room opens into a designed page and the speaker stays in front.

What a takeover beat does, in order (every time is a frame, anchored to the beat's words):
  1. reveal   the page (paper ground, faint grid) opens through a circle that starts behind the speaker's head
              (or a point you name) while the speaker stays on top as a live cut-out (assets/tko_<seg>.webm, bake.py)
  2. step     the speaker steps aside: the cut-out settles to a smaller scale and slides left, then keeps a slow push
              (depth against the page, which pushes less)
  3. page     a kicker types on (mono caps), a ghost outline numeral rolls in top right, a side tracker staggers in
              and the current step fills like a progress pill (the previous one gets a tick)
  4. words    huge serif words BEHIND the head, letter by letter out of a mask with blur; when the next word lands the
              previous one recedes (smaller, higher, blurred) and stays behind it as a ghost
  5. chart    a line chart draws on the page with a lead dot; where it crosses the limit it turns red, the chart jolts,
              the limit label stamps and a serif note with a drawn arrow names what it means
  6. rack     when a later word lands, the chart racks out of focus so the word owns the frame

Config (project.json "editorial"):
  "tracker": {"title": "5 THINGS", "items": ["Blood work", "Deadline"], "count": 5}
  "beats": {"n1a": {"scene": "takeover", "kicker": "5 THINGS TO GET IN SHAPE", "step": 1,
                    "words": [{"at": 0, "text": "_No. 1_"}, {"at": "@blood", "text": "BLOOD|WORK"}]},
            "n1d": {"scene": "takeover", "step": 1, "chart": {"title": "FASTING INSULIN", "unit": "uIU/mL",
                    "values": [3.4, 4.2, 5.3, 6.4, 7.6, 8.9, 9.8], "limit": 7, "at": "@insulin", "cross": "@over",
                    "note": "insulin resistance", "note_at": "@that"}}}
Optional per beat: "page" (palette key, default "bone"), "reveal": {"from": "head" | "chest" | [x, y], "delay": s},
"subject": {"scale": 0.9, "x": -150}, "step_at": "@2", "rack": true. Defaults: style.json "takeover".

Rules kept: nothing over the face (the tracker sits in the right column the step-aside frees, captions stay under the
chin), Reels safe zone, words behind the head (the head may break their foot, never the face), every entrance
lands a frame before its word, SFX light (reveal, word thumps, the chart cross).
"""
import math
import random
import re

import kit  # noqa: E402  (stylekit, on sys.path via plan.py)
from kit import FPS, esc  # noqa: E402
import etheme as theme  # noqa: E402

W, H = 1080, 1920
SLIDE_AT = 0.55          # the step-aside starts when the circle has covered the speaker (share of the reveal)


# ----------------------------------------------------------------------------- easing (same curves as GSAP)
def e_inout2(p):
    p = min(max(p, 0.0), 1.0)
    return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2


def e_inout3(p):
    p = min(max(p, 0.0), 1.0)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def e_expo_out(p):
    p = min(max(p, 0.0), 1.0)
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def T(f):
    """frame -> timeline time (half a frame early, so frame f shows it)."""
    return kit.fsnap(f)


def deep(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


# ----------------------------------------------------------------------------- planning (frames, geometry)
def plan_all(pl):
    """Plan every takeover segment; fills pl.subj_xf (frame -> cut-out transform) for the face mapping."""
    base = pl.cfg.get("takeover", {})
    out = []
    for s in pl.segs:
        if s["scene"] != "takeover":
            continue
        out.append(plan_one(pl, s, deep(base, {k: v for k, v in s["beat"].items() if k in ("reveal", "subject", "words_style")})))
    return out


def plan_one(pl, s, cfg):
    b = s["beat"]
    f0, f1 = s["f0"], s["f1"]
    ax, ay = s["anchor"]
    rv = cfg["reveal"]
    r0 = min(f1 - 8, f0 + max(1, int(round(float(rv.get("delay", 0.22)) * FPS))))
    rdur = max(8, int(round(float(rv.get("dur", 0.6)) * FPS)))
    head_c = ((s["head_top"] + s["brow"]) / 2)
    frm = rv.get("from", "head")
    if isinstance(frm, (list, tuple)):
        px, py = float(frm[0]), float(frm[1])
    elif frm == "chest":
        px, py = ax, s["chin"] + 0.9 * (s["chin"] - s["brow"])
    else:
        px, py = ax, head_c
    sub = cfg["subject"]
    K, DX = float(sub.get("scale", 0.9)), float(sub.get("x", -150))
    push = float(sub.get("push", 0.025))
    fs = r0 + int(round(SLIDE_AT * rdur))
    fe = min(f1 - 1, fs + max(6, int(round(float(sub.get("slide_s", 0.62)) * FPS))))
    ox, oy = ax, float(H)
    rows = []
    for f in range(f0, f1):
        if f < fs:
            k, dx = 1.0, 0.0
        elif f < fe:
            e = e_inout3((f - fs) / max(1, fe - fs))
            k, dx = 1 + (K - 1) * e, DX * e
        else:
            p = (f - fe) / max(1, f1 - fe)
            k, dx = K * (1 + push * p), DX
        k, dx = round(k, 4), round(dx, 1)
        pl.subj_xf[f] = (k, dx, 0.0, ox, oy)
        if not rows or rows[-1][1:] != [k, dx]:
            rows.append([f, k, dx])

    def scr(y):                  # settled screen y of a point on the speaker
        return oy + (y - oy) * K
    head_top, brow = scr(s["head_top"]), scr(s["brow"])
    hx0, hx1 = ox + (s["head_x"][0] - ox) * K + DX, ox + (s["head_x"][1] - ox) * K + DX
    t = {"seg": s["id"], "f0": f0, "f1": f1, "reveal": [r0, r0 + rdur], "point": [round(px), round(py)],
         "slide": [fs, fe], "xf_rows": rows, "origin": [round(ox, 1), round(oy, 1)], "K": K, "DX": DX,
         "head_top": head_top, "brow": brow, "head_x": [hx0, hx1], "page": b.get("page", cfg.get("page", "bone")),
         "step": b.get("step"), "webm": f"assets/tko_{s['id']}.webm", "beat": b, "cfg": cfg}
    # words behind the head
    wc = cfg["words"]
    t["word_bottom"] = round(head_top + wc["overlap"] * (brow - head_top))
    words = []
    for i, w in enumerate(b.get("words", [])):
        words.append({"i": i, "f": pl.at(w.get("at", 0), s), "text": w["text"], "cx": w.get("cx", wc.get("cx", 540))})
    words.sort(key=lambda w: w["f"])
    for w in words:
        w["f"] = max(w["f"], r0 + 4)
    t["words"] = words
    # step (tracker) timing
    if t["step"]:
        sa = b.get("step_at")
        t["step_f"] = max(pl.at(sa, s) if sa is not None else r0 + int(0.5 * FPS), r0 + 20)   # after the rows are in
    # chart
    ch = b.get("chart")
    if ch:
        c = dict(ch)
        c["f"] = max(pl.at(c.get("at", 0), s), r0 + 6)
        c["cross_f"] = pl.at(c["cross"], s) if c.get("cross") is not None else None
        c["note_f"] = pl.at(c["note_at"], s) if c.get("note_at") is not None else None
        # the chart keeps clear of the face for its whole life (the cut-out is still big before it steps aside)
        tops = []
        for f in range(c["f"], f1):
            fb = pl.face_box(f)
            if fb:
                tops.append(fb[1] - 0.24 * (fb[3] - fb[1]))
        c["ybot_max"] = int(min(tops) - 8 - 74) if tops else None
        t["chart"] = c
    return t


# ----------------------------------------------------------------------------- css
def css(tok, cfg):
    return f"""
/* takeover (Motion v2) */
.tkx{{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:0;visibility:hidden;z-index:3}}
.tkpage{{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden}}
.tkgrid{{position:absolute;inset:0;background-size:60px 60px}}
.tksw{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.tksw video{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}}
.tkghost{{position:absolute;right:28px;top:292px;width:560px;height:420px;overflow:hidden}}
.tkghost .col{{position:absolute;left:0;top:0;width:560px}}
.tkghost .col div{{height:420px;font:italic 900 400px/420px var(--fs);letter-spacing:-.03em;color:transparent;text-align:right}}
.tkkick{{position:absolute;left:64px;top:268px;width:952px;display:flex;justify-content:space-between;gap:32px;white-space:nowrap;
  font:600 26px/1 var(--fm);letter-spacing:.18em}}
.tkkick .rc{{visibility:hidden}}
.tkcont{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 600px}}
.tkw{{position:absolute;left:0;width:1080px;font-family:var(--fs);display:flex;flex-direction:column;align-items:center;transform-origin:540px 100%}}
.tkw .ln{{display:block;overflow:hidden;white-space:nowrap;line-height:.86;padding:.1em .07em 0}}
.tkw .rc{{display:inline-block;will-change:transform}}
.tkw .hv{{font-weight:900;letter-spacing:-.025em}}
.tkw .it{{font-style:italic;font-weight:700;letter-spacing:-.01em}}
.tktr{{position:absolute}}
.tkst{{position:relative;height:54px;margin-bottom:12px;display:flex;align-items:center;gap:16px;padding-left:6px;white-space:nowrap}}
.tkst .bg{{position:absolute;left:0;top:0;width:100%;height:100%;border-radius:27px;transform-origin:0 50%;transform:scaleX(0)}}
.tkst .n{{position:relative;width:42px;height:42px;border-radius:21px;display:flex;align-items:center;justify-content:center;
  font:700 19px/1 var(--fm);flex:none}}
.tkst .l{{position:relative;font:700 27px/1 var(--fu);letter-spacing:-.015em}}
.tkst .dash{{position:relative;width:86px;height:3px;border-radius:2px}}
.tkst .ok{{position:relative;margin-left:-6px;display:flex}}
.tknote{{position:absolute;white-space:nowrap;font-family:var(--fs);font:italic 700 62px/1 var(--fs);letter-spacing:-.01em}}
.tknote .ln{{display:block;overflow:hidden;padding:.08em .06em .1em}}
.tkchart text{{font-family:var(--fm)}}
"""


# ----------------------------------------------------------------------------- html + timeline
def _runs(line):
    out = []
    for p in re.split(r"(_[^_]+_)", line):
        if not p:
            continue
        if p.startswith("_") and p.endswith("_") and len(p) > 2:
            out.append((p[1:-1], True))
        else:
            out.append((p, False))
    return out


def _chars(text, cls, cid):
    return "".join(f'<span class="rc {cls}" id="{cid}{i}">{esc(c) if c != " " else "&nbsp;"}</span>' for i, c in enumerate(text))


def words_html(t, sch, wc):
    out, sid = [], t["seg"]
    for w in t["words"]:
        wid = f"tkW{sid}_{w['i']}"
        lines = w["text"].split("|")
        lh = []
        n = 0
        for li, line in enumerate(lines):
            runs = _runs(line)
            italic_only = all(it for _, it in runs)
            px = wc["italic_px"] if italic_only else wc["max_px"]
            spans = []
            for txt, it in runs:
                spans.append(_chars(txt, "it" if it else "hv", f"{wid}c{n}_"))
                n += 1
            lh.append(f'<div class="ln" data-fit="{wc["max_w"]},{wc["min_px"]}" style="font-size:{px}px">{"".join(spans)}</div>')
        out.append(f'<div class="tkw el" id="{wid}" style="bottom:{H - t["word_bottom"]}px;color:{sch["type"]}" '
                   f'{kit.box("behind", w["f"] / FPS, t["f1"] / FPS)}>{"".join(lh)}</div>')
    css_ = f'#tk{sid} .tkw .it{{color:{sch["accent"]}}}'
    return "".join(out), css_


def tracker_html(t, tok, sch, trc):
    sid = t["seg"]
    items = list(trc.get("items") or [])
    count = max(int(trc.get("count") or 0), len(items), int(t["step"] or 0))
    if not count:
        return "", 0
    rows = []
    for i in range(count):
        lab = items[i] if i < len(items) else ""
        lab_html = (f'<span class="l" id="tkT{sid}_{i}l" data-fit="{trc["w"] - 80},18">{esc(lab)}</span>' if lab
                    else f'<span class="dash" style="background:{theme.rgba(tok["ink"], .12)}"></span>')
        rows.append(f'<div class="tkst" id="tkT{sid}_{i}"><div class="bg" id="tkT{sid}_{i}b" style="background:{sch["accent"]}"></div>'
                    f'<div class="n" id="tkT{sid}_{i}n" style="border:2.5px solid {theme.rgba(tok["ink"], .22)};color:{theme.rgba(tok["ink"], .55)}">'
                    f'{i + 1:02d}</div>{lab_html}</div>')
    h = count * 66 - 12
    html = (f'<div class="tktr" id="tkT{sid}" style="left:{trc["x"]}px;top:{trc["top"]}px;width:{trc["w"]}px" '
            f'{kit.box("card", t["reveal"][0] / FPS, t["f1"] / FPS)}>{"".join(rows)}</div>')
    return html, h


def chart_geom(c, ytop, ybot, x0=96, x1=984):
    vals = [float(v) for v in c["values"]]
    lim = float(c.get("limit")) if c.get("limit") is not None else None
    hi = max(vals + ([lim] if lim is not None else [])) * 1.04
    lo = float(c["min"]) if c.get("min") is not None else min(vals) * 0.55   # use the height: the line is the hero
    pt, pb = ytop + 74, ybot

    def y(v):
        return pb - (v - lo) / max(1e-6, hi - lo) * (pb - pt)
    xs = [x0 + 30 + i * (x1 - x0 - 60) / max(1, len(vals) - 1) for i in range(len(vals))]
    P = [(x, y(v)) for x, v in zip(xs, vals)]
    # Catmull-Rom -> dense polyline
    pts = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(0, i - 1)], P[i], P[i + 1], P[min(len(P) - 1, i + 2)]
        for k in range(16):
            u = k / 16
            u2, u3 = u * u, u * u * u
            pts.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * u + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * u2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * u3) for j in (0, 1)))
    pts.append(P[-1])
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(seg)
    cum = [0.0]
    for d in seg:
        cum.append(cum[-1] + d)
    ly = y(lim) if lim is not None else None
    cfrac = None
    if ly is not None:
        for i in range(1, len(pts)):
            if pts[i][1] < ly <= pts[i - 1][1]:
                a, b = pts[i - 1], pts[i]
                u = (pts[i - 1][1] - ly) / max(1e-6, pts[i - 1][1] - pts[i][1])
                cfrac = (cum[i - 1] + u * seg[i - 1]) / total
                break

    def at(p):
        d = p * total
        for i in range(1, len(cum)):
            if cum[i] >= d:
                u = (d - cum[i - 1]) / max(1e-6, seg[i - 1])
                return (pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u)
        return pts[-1]
    return {"pts": pts, "ly": ly, "cfrac": cfrac, "at": at, "x0": x0, "x1": x1, "pt": pt, "pb": pb, "P": P}


def chart_build(t, c, tok, sch, tl, cues, events, ytop, ybot):
    sid = t["seg"]
    g = chart_geom(c, ytop, ybot)
    ink, flag, acc = tok["ink"], tok["flag"], sch["accent"]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in g["pts"])
    ly = g["ly"]
    above = [p for p in g["pts"] if ly is not None and p[1] < ly]
    area = ""
    if above and ly is not None:
        area = (f"M{g['pts'][0][0]:.1f},{ly:.1f} L" + " L".join(f"{x:.1f},{min(y, ly):.1f}" for x, y in g["pts"])
                + f" L{g['pts'][-1][0]:.1f},{ly:.1f} Z")
    lim_lab = esc(c.get("limit_label", f"{c.get('limit', '')}".rstrip("0").rstrip(".")))
    svg = [f'<svg class="tkchart" viewBox="0 0 1080 1920" width="1080" height="1920" style="position:absolute;left:0;top:0;overflow:visible">',
           f'<defs><filter id="tkGlow{sid}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="10"/></filter>',
           f'<clipPath id="tkAbove{sid}"><rect x="0" y="0" width="1080" height="{ly if ly is not None else 0:.1f}"/></clipPath></defs>',
           f'<text x="{g["x0"]}" y="{ytop + 26}" font-size="26" font-weight="700" letter-spacing="4.5" fill="{acc}" id="tkCt{sid}">{esc(c.get("title", ""))}</text>',
           f'<text x="{g["x1"]}" y="{ytop + 26}" font-size="22" font-weight="600" letter-spacing="3" text-anchor="end" fill="{theme.rgba(ink, .45)}" id="tkCu{sid}">{esc(c.get("unit", ""))}</text>',
           f'<path id="tkCb{sid}" d="M{g["x0"]},{g["pb"]:.1f} L{g["x1"]},{g["pb"]:.1f}" stroke="{theme.rgba(ink, .2)}" stroke-width="3" fill="none" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>']
    if ly is not None:
        svg.append(f'<path id="tkCa{sid}" d="{area}" fill="{theme.rgba(flag, .16)}" clip-path="url(#tkAbove{sid})" opacity="0"/>')
        svg.append(f'<path id="tkCl{sid}" d="M{g["x0"]},{ly:.1f} L{g["x1"]},{ly:.1f}" stroke="{theme.rgba(ink, .5)}" stroke-width="4" fill="none" stroke-dasharray="14 12" opacity="0"/>')
    svg.append(f'<path id="tkCg{sid}" d="{d}" stroke="{flag}" stroke-width="26" fill="none" stroke-linecap="round" filter="url(#tkGlow{sid})" clip-path="url(#tkAbove{sid})" opacity="0"/>')
    svg.append(f'<path id="tkCp{sid}" class="tkdraw" d="{d}" stroke="{ink}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>')
    if ly is not None:
        svg.append(f'<path id="tkCr{sid}" class="tkdraw" d="{d}" stroke="{flag}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" clip-path="url(#tkAbove{sid})"/>')
    svg.append(f'<circle id="tkCdR{sid}" cx="0" cy="0" r="16" fill="none" stroke="{flag}" stroke-width="4" opacity="0"/>')
    svg.append(f'<circle id="tkCd{sid}" cx="{g["pts"][0][0]:.1f}" cy="{g["pts"][0][1]:.1f}" r="15" fill="{flag}" opacity="0"/>')
    note_html = ""
    arrow = None
    if c.get("note") and ly is not None and above:
        tgt = above[len(above) // 3]
        nx0, ny = g["x0"] + 2, g["pt"] - 6                  # upper left: the line is still low there
        nw = int(len(c["note"]) * 62 * 0.42)                 # serif italic estimate
        sx, sy = nx0 + nw + 18, ny + 40
        ex, ey = tgt[0] - 10, tgt[1] - 22
        mx, my = (sx + ex) / 2, min(sy, ey) - 50
        ang = math.atan2(ey - my, ex - mx)
        hx = [ex - 26 * math.cos(ang - 0.45), ey - 26 * math.sin(ang - 0.45)]
        hy = [ex - 26 * math.cos(ang + 0.45), ey - 26 * math.sin(ang + 0.45)]
        arrow = f"M{sx:.1f},{sy:.1f} Q{mx:.1f},{my:.1f} {ex:.1f},{ey:.1f} M{hx[0]:.1f},{hx[1]:.1f} L{ex:.1f},{ey:.1f} L{hy[0]:.1f},{hy[1]:.1f}"
        svg.append(f'<path id="tkCn{sid}" d="{arrow}" stroke="{flag}" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>')
        note_html = (f'<div class="tknote el" id="tkCN{sid}" style="left:{nx0}px;top:{ny}px;color:{flag}" '
                     f'{kit.box("text", (c["note_f"] or t["f1"] - 1) / FPS, t["f1"] / FPS)}><span class="ln">'
                     f'{_chars(c["note"], "", f"tkCN{sid}c")}</span></div>')
    lab_html = ""
    if ly is not None:
        lab_html = (f'<div class="el" id="tkCL{sid}" style="position:absolute;right:{W - g["x1"]}px;top:{ly + 14:.0f}px;'
                    f'font:italic 900 128px/1 var(--fs);color:{flag};transform-origin:70% 20%" {kit.box("text", c["f"] / FPS, t["f1"] / FPS)}>{lim_lab}</div>')
    svg.append("</svg>")
    hit = (f'<div style="position:absolute;left:{g["x0"] - 26}px;top:{ytop}px;width:{g["x1"] - g["x0"] + 52}px;height:{ybot - ytop + 8}px" '
           f'{kit.box("card", c["f"] / FPS, t["f1"] / FPS, readable=False)}></div>')
    html = f'<div class="tkcont" id="tkC{sid}">' + hit + "".join(svg) + lab_html + note_html + "</div>"

    # ---- timeline
    fa, fc, fn = c["f"], c.get("cross_f"), c.get("note_f")
    tl.set(f"#tkC{sid}", fa / FPS, {"visibility": "visible", "opacity": 1})
    tl.raw(f'tl.fromTo("#tkC{sid}",{{y:70,scale:.96,filter:"blur(10px)"}},{{y:0,scale:1,filter:"blur(0px)",duration:.5,ease:"expo.out",immediateRender:false}},{T(fa)});')
    tl.raw(f'tl.fromTo("#tkCb{sid}",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:.45,ease:"power2.inOut",immediateRender:false}},{T(fa)});')
    tl.raw(f'tl.fromTo(["#tkCt{sid}","#tkCu{sid}"],{{opacity:0,y:18}},{{opacity:1,y:0,duration:.4,ease:"expo.out",stagger:.06,immediateRender:false}},{T(fa)});')
    events.append((fa, "enter", f"{sid} chart", [70, ytop, 940, ybot - ytop + 10], None))
    cues.append((fa, "swish", -8))
    if ly is not None:
        tl.raw(f'tl.fromTo("#tkCl{sid}",{{opacity:0,strokeDashoffset:120}},{{opacity:1,strokeDashoffset:0,duration:.5,ease:"expo.out",immediateRender:false}},{T(fa + 4)});')
    # draw: up to the crossing on the build-up, the rest snaps after the cross word
    cf = g["cfrac"]
    paths = f'["#tkCp{sid}"' + (f',"#tkCr{sid}"' if ly is not None else "") + "]"
    two = cf is not None and fc is not None and fc - fa >= 8
    if two:
        d1 = (fc - fa) / FPS
        d2 = 0.42
        tl.raw(f'tl.fromTo({paths},{{strokeDashoffset:1}},{{strokeDashoffset:{1 - cf:.4f},duration:{d1:.3f},ease:"power2.inOut",immediateRender:false}},{T(fa + 2)});')
        tl.raw(f'tl.to({paths},{{strokeDashoffset:0,duration:{d2},ease:"expo.out"}},{T(fc + 2)});')
        prog = lambda f: (cf * e_inout2((f - fa - 2) / (d1 * FPS)) if f < fc + 2 else cf + (1 - cf) * e_expo_out((f - fc - 2) / (d2 * FPS)))  # noqa: E731
        end_f = fc + 2 + int(d2 * FPS) + 1
    else:
        d1 = 0.9
        tl.raw(f'tl.fromTo({paths},{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:{d1},ease:"power2.inOut",immediateRender:false}},{T(fa + 2)});')
        prog = lambda f: e_inout2((f - fa - 2) / (d1 * FPS))  # noqa: E731
        end_f = fa + 2 + int(d1 * FPS) + 1
    tl.set(f"#tkCd{sid}", (fa + 2) / FPS, {"opacity": 1})
    for f in range(fa + 2, min(end_f, t["f1"])):
        x, y = g["at"](max(0.0, min(1.0, prog(f))))
        tl.set(f"#tkCd{sid}", f / FPS, {"attr": {"cx": round(x, 1), "cy": round(y, 1)}})
    if ly is not None and fc is not None:
        tl.raw(f'tl.to("#tkCg{sid}",{{opacity:.55,duration:.3,ease:"power2.out"}},{T(fc + 2)});')
        tl.raw(f'tl.to("#tkCa{sid}",{{opacity:1,duration:.45,ease:"power2.out"}},{T(fc + 4)});')
        tl.raw(f'tl.to("#tkCd{sid}",{{attr:{{r:20}},duration:.12,ease:"power2.out",yoyo:true,repeat:1}},{T(fc + 2)});')
        # the chart jolts on the cross (seeded, decaying)
        rnd = random.Random(31)
        for i in range(6):
            k = 1 - i / 6
            tl.set(f"#tkC{sid}", (fc + 2 + i) / FPS, {"x": round((rnd.random() - .5) * 18 * k, 1), "y": round((rnd.random() - .5) * 14 * k, 1)})
        tl.set(f"#tkC{sid}", (fc + 8) / FPS, {"x": 0, "y": 0})
        # the limit label stamps
        tl.set(f"#tkCL{sid}", (fc + 1) / FPS, {"visibility": "visible"})
        tl.raw(f'tl.fromTo("#tkCL{sid}",{{opacity:.4,scale:2.2,rotation:-8,filter:"blur(18px)"}},{{opacity:1,scale:1,rotation:-3,filter:"blur(0px)",duration:.24,ease:"power4.out",immediateRender:false}},{T(fc + 1)});')
        events.append((fc + 1, "enter", f"{sid} limit", [g["x1"] - 700, int(ly + 14), 700, 140], f"#tkCL{sid}"))
        cues.append((fc + 2, "pop_lo", -3))
    if arrow and fn:
        fn = max(fn, (fc or fa) + 8)
        tl.set(f"#tkCN{sid}", fn / FPS, {"visibility": "visible", "opacity": 1})
        tl.raw(f'tl.fromTo("#tkCN{sid} .rc",{{yPercent:110,rotation:5,filter:"blur(8px)"}},{{yPercent:0,rotation:0,filter:"blur(0px)",duration:.42,ease:"expo.out",stagger:.022,immediateRender:false}},{T(fn)});')
        tl.raw(f'tl.fromTo("#tkCn{sid}",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:.38,ease:"power2.inOut",immediateRender:false}},{T(fn + 5)});')
        events.append((fn, "tick", f"{sid} note", [g["x0"], int(g["pt"] - 6), 430, 80], None))
    return html, g


def build(pl, tok, tl, cues):
    """-> (camera_html, css, events[(frame, kind, label, region, sel)], content_tops {seg: y}) for every takeover."""
    if not pl.takeovers:
        return "", "", [], {}
    cfg_all = pl.cfg.get("takeover", {})
    trc = deep(cfg_all.get("tracker", {}), pl.cfg.get("tracker", {}))
    html, extra_css, events, tops = [], [css(tok, cfg_all)], [], {}
    for n, t in enumerate(pl.takeovers):
        sid, f0, f1 = t["seg"], t["f0"], t["f1"]
        b, cfg = t["beat"], t["cfg"]
        sch = theme.scheme(tok, pl.cfg, t["page"])
        ink = tok["ink"]
        r0, r1 = t["reveal"]
        px, py = t["point"]
        light = theme.mix(sch["plate"], "#FFFFFF", 0.42)
        dark = theme.mix(sch["plate"], "#000000", 0.07)
        ground = f"radial-gradient(120% 80% at 70% 22%,{light} 0%,{sch['plate']} 56%,{dark} 100%)"
        grid = (f"linear-gradient({theme.rgba(ink, .045)} 1px,transparent 1px),"
                f"linear-gradient(90deg,{theme.rgba(ink, .045)} 1px,transparent 1px)")
        parts = [f'<div class="tkx" id="tk{sid}">',
                 f'<div class="tkpage" id="tkP{sid}" style="background:{ground};clip-path:circle(0px at {px}px {py}px)">',
                 f'<div class="tkgrid" id="tkGr{sid}" style="background-image:{grid}"></div>']
        # ghost numeral (decorative outline), kicker
        step = int(t["step"] or 0)
        ghost = cfg.get("ghost", True) and not t.get("chart")      # the chart owns the top of the page
        if step and ghost:
            nums = [f"{step - 1:02d}", f"{step:02d}"] if step > 1 else [f"{step:02d}"]
            stroke = f"-webkit-text-stroke:3px {theme.rgba(sch['accent'], .26)}"
            parts.append(f'<div class="tkghost" id="tkG{sid}"><div class="col" id="tkGc{sid}">'
                         + "".join(f'<div style="{stroke}">{x}</div>' for x in nums) + "</div></div>")
        kl = b.get("kicker", trc.get("title", ""))
        count = max(int(trc.get("count") or 0), len(trc.get("items") or []), step)
        kr = f"PART {step:02d} / {count:02d}" if step and count else ""
        if kl or kr:
            parts.append(f'<div class="tkkick" id="tkK{sid}" style="color:{theme.rgba(ink, .55)}" {kit.box("text", (r0 + 8) / FPS, f1 / FPS)}>'
                         f'<span>{_chars(kl, "", f"tkKl{sid}c")}</span> <span style="color:{sch["accent"]}">{_chars(kr, "", f"tkKr{sid}c")}</span></div>')
        # chart (content group: racks out of focus when a later word lands)
        ctop = int(cfg.get("content_top", 330))
        tops[sid] = ctop
        ch = t.get("chart")
        if ch:
            ybot = min(int(t["head_top"]) - 60, ctop + 500, ch.get("ybot_max") or 9999)
            chart_html, _g = chart_build(t, ch, tok, sch, tl, cues, events, ctop, ybot)
            parts.append(chart_html)
        wh, wcss = words_html(t, sch, cfg["words"])
        extra_css.append(wcss)
        parts.append(f'<div id="tkWs{sid}">{wh}</div>')
        parts.append("</div>")                          # /page
        parts.append(f'<div class="tksw" id="tkSW{sid}" style="transform-origin:{t["origin"][0]}px {t["origin"][1]}px;'
                     f'filter:drop-shadow(0 30px 44px {theme.rgba(ink, .26)})">'
                     f'<video id="tkS{sid}" src="{t["webm"]}" muted playsinline data-start="{max(0.0, f0 / FPS - 0.002):.3f}" '
                     f'data-duration="{kit.duration_str(f1 - f0 + 3)}" data-track-index="{10 + n}"></video></div>')
        trh, trh_h = tracker_html(t, tok, sch, trc) if step else ("", 0)
        parts.append(f'<div id="tkF{sid}" style="position:absolute;left:0;top:0;width:1080px;height:1920px">{trh}</div>')
        parts.append("</div>")
        html.append("".join(parts))

        # ---------------- timeline
        tl.set(f"#tk{sid}", f0 / FPS, {"opacity": 1, "visibility": "visible"})
        tl.set(f"#tk{sid}", f1 / FPS, {"opacity": 0, "visibility": "hidden"})
        # 1. reveal: the page opens through a circle from behind the head
        rd = (r1 - r0) / FPS
        tl.raw(f'tl.fromTo("#tkP{sid}",{{clipPath:"circle(0px at {px}px {py}px)"}},{{clipPath:"circle(2300px at {px}px {py}px)",'
               f'duration:{rd:.3f},ease:"power2.inOut",immediateRender:false}},{T(r0)});')
        tl.raw(f'tl.fromTo("#tkGr{sid}",{{scale:1.12}},{{scale:1,duration:{rd + .5:.3f},ease:"expo.out",immediateRender:false}},{T(r0)});')
        mid = r0 + int((r1 - r0) * 0.5)
        events.append((mid, "enter", f"{sid} takeover page", [0, 0, W, H], None))
        cues.append((r0 + 2, "swish", -3))
        # 2. the cut-out steps aside (per-frame keys, the same numbers QA maps the face through)
        o = t["origin"]
        for f, k, dx in t["xf_rows"]:
            tl.set(f"#tkSW{sid}", f / FPS, {"transformOrigin": f"{o[0]}px {o[1]}px", "scale": k, "x": dx})
        fs, fe = t["slide"]
        if fe > fs:
            events.append((fs + 3, "tick", f"{sid} step aside", [0, 760, W, 1160], None))
        # page breathes less than the speaker (parallax)
        tl.raw(f'tl.fromTo("#tkP{sid}",{{scale:1.0}},{{scale:1.012,duration:{max(.3, (f1 - r0) / FPS):.3f},ease:"none",immediateRender:false}},{T(r0)});')
        # 3. ghost numeral + kicker + tracker
        if step and ghost:
            if step == 1:
                tl.raw(f'tl.fromTo("#tkGc{sid}",{{yPercent:60}},{{yPercent:0,duration:.7,ease:"expo.out",immediateRender:false}},{T(r0 + 2)});')
            tl.raw(f'tl.fromTo("#tkG{sid}",{{y:70,opacity:0}},{{y:0,opacity:1,duration:.8,ease:"expo.out",immediateRender:false}},{T(r0 + 2)});')
        ktxt = (kl or "") + (kr or "")
        if ktxt:
            fk = r0 + 8
            nk = len(kl or "")
            for i in range(nk):
                tl.set(f"#tkKl{sid}c{i}", (fk + int(i * 0.75)) / FPS, {"visibility": "visible"})
            for i in range(len(kr or "")):
                tl.set(f"#tkKr{sid}c{i}", (fk + int(i * 0.75)) / FPS, {"visibility": "visible"})
        if step:
            tr0 = r0 + 10
            tl.set(f"#tkT{sid} .tkst", f0 / FPS, {"opacity": 0})
            tl.raw(f'tl.fromTo("#tkT{sid} .tkst",{{opacity:.35,x:70,filter:"blur(8px)"}},{{opacity:1,x:0,filter:"blur(0px)",duration:.5,ease:"expo.out",stagger:.06,immediateRender:false}},{T(tr0)});')
            events.append((tr0, "tick", f"{sid} tracker", [trc["x"], trc["top"], trc["w"], 54], None))
            cues.append((tr0, "tick", -10))
            done_col = theme.rgba(ink, .72)

            def fill(i, f, on=True, dur=.42):
                if on:
                    tl.raw(f'tl.to("#tkT{sid}_{i}b",{{scaleX:1,duration:{dur},ease:"expo.out"}},{T(f)});')
                    tl.raw(f'tl.to("#tkT{sid}_{i}n",{{color:"{tok["cream"]}",borderColor:"{theme.rgba(tok["cream"], .6)}",duration:.2}},{T(f)});')
                    tl.raw(f'tl.to("#tkT{sid}_{i}l",{{color:"{tok["cream"]}",duration:.2}},{T(f)});')
                    tl.raw(f'tl.fromTo("#tkT{sid}_{i}",{{scale:1}},{{scale:1.07,duration:.12,ease:"power2.out",yoyo:true,repeat:1,immediateRender:false}},{T(f)});')
                else:
                    tl.raw(f'tl.to("#tkT{sid}_{i}b",{{scaleX:0,duration:.26,ease:"power3.in"}},{T(f)});')
                    tl.raw(f'tl.to(["#tkT{sid}_{i}n","#tkT{sid}_{i}l"],{{color:"{done_col}",borderColor:"{theme.rgba(ink, .4)}",duration:.2}},{T(f + 4)});')
            sf = t["step_f"]
            for i in range(min(count, len(trc.get("items") or []))):   # labels: dim; done rows darker
                tl.set(f"#tkT{sid}_{i}l", 0, {"color": done_col if i < step - 1 else theme.rgba(ink, .5)})
            if step > 1:
                tl.set(f"#tkT{sid}_{step - 2}b", 0, {"scaleX": 1})
                tl.set(f"#tkT{sid}_{step - 2}n", 0, {"color": tok["cream"], "borderColor": theme.rgba(tok["cream"], .6)})
                if step - 2 < len(trc.get("items") or []):
                    tl.set(f"#tkT{sid}_{step - 2}l", 0, {"color": tok["cream"]})
                fill(step - 2, sf - 4, on=False)
                if ghost:
                    tl.raw(f'tl.to("#tkGc{sid}",{{yPercent:-50,duration:.55,ease:"expo.inOut"}},{T(sf - 3)});')
                # kicker part number flips with the step (it typed the new one already)
            fill(step - 1, sf)
            ry = trc["top"] + 66 * (step - 1)
            events.append((sf, "tick", f"{sid} step {step:02d}", [trc["x"], ry, trc["w"], 54], None))
            cues.append((sf, "pop_hi", -7))
        # 4. words behind the head; the previous one recedes into a blurred ghost
        prev = []
        for wi, w in enumerate(t["words"]):
            wid, fw = f"tkW{sid}_{w['i']}", w["f"]
            nxt = t["words"][wi + 1]["f"] if wi + 1 < len(t["words"]) else f1
            tl.set(f"#{wid}", fw / FPS, {"visibility": "visible", "opacity": 1})
            italic = all(it for ln in w["text"].split("|") for _, it in _runs(ln))
            if italic:
                tl.raw(f'tl.fromTo("#{wid} .rc",{{yPercent:115,rotation:7,filter:"blur(10px)"}},{{yPercent:0,rotation:0,filter:"blur(0px)",duration:.5,ease:"expo.out",stagger:.034,immediateRender:false}},{T(fw)});')
            else:
                tl.raw(f'tl.fromTo("#{wid} .rc",{{yPercent:120,scaleY:1.5,filter:"blur(14px)"}},{{yPercent:0,scaleY:1,filter:"blur(0px)",duration:.5,ease:"expo.out",stagger:.028,immediateRender:false}},{T(fw)});')
            tl.raw(f'tl.fromTo("#{wid}",{{scale:1}},{{scale:1.04,duration:{max(.1, (nxt - fw - 1) / FPS):.3f},ease:"none",immediateRender:false}},{T(fw)});')
            for j, p in enumerate(reversed(prev)):
                if j == 0:
                    tl.raw(f'tl.to("#{p}",{{scale:.7,y:-190,filter:"blur(12px)",opacity:.22,duration:.5,ease:"power2.inOut"}},{T(fw)});')
                else:
                    tl.raw(f'tl.to("#{p}",{{opacity:0,duration:.3,ease:"power3.in"}},{T(fw)});')
            if ch and cfg.get("rack", True) and fw > ch["f"] + 6:
                tl.raw(f'tl.to("#tkC{sid}",{{filter:"blur(7px)",opacity:.38,duration:.35,ease:"power2.inOut"}},{T(fw - 2)});')
            events.append((fw, "enter", f"{sid} word {w['text']}", [40, t["word_bottom"] - 300, 1000, 300], None))
            cues.append((fw, "thump", -6))
            prev.append(wid)
    return "".join(html), "\n".join(extra_css), events, tops
