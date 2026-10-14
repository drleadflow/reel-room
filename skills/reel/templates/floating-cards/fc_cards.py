"""Floating Cards: frosted UI cards with real 3D motion (Motion v2).

Every card is three nested layers, each owning its own properties (no two tweens ever fight over one property):
  .kw  wrapper   home position; re-arrangements (stack, fan, dock, dim) and the strike-tumble exit
  .kf  float     the idle orbit after landing (sine yoyo on y, rotationY, rotationX, rotation; seeded per card)
  .card          the 3D fly-in (perspective, rotateY/X, z depth, blur as motion blur, back.out landing overshoot),
                 the fly-away exit; .ksh under it is the contact shadow that tightens as the card lands

Cards are grouped into clusters (one topic around the head). A cluster is the beat's hero: each entrance event's
region spans the cluster's full width at the entering card's height (QA hero_scale measures the cluster, the same
union rule the split engine uses for a chart and its labels).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
import kit  # noqa: E402
from kit import FPS, esc  # noqa: E402

PERSP = 1100
LAND = 0.5          # landing duration (s)
ICONS = {  # 24x24 stroke glyphs (generic, no brands)
    "stethoscope": '<path d="M6 3v5a4 4 0 0 0 8 0V3"/><path d="M10 12v2.5a5 5 0 0 0 10 0V12"/><circle cx="20" cy="10" r="2"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2.5"/><path d="M9 3h6v3H9z"/><path d="M9 13.5l2 2 4-4.5"/>',
    "tube": '<path d="M9 3h6"/><path d="M10 3v13.5a2 2 0 0 0 4 0V3"/><path d="M10 11h4"/>',
    "drop": '<path d="M12 3.5c3 4.2 6 7.2 6 10.6a6 6 0 0 1-12 0c0-3.4 3-6.4 6-10.6z"/><path d="M9.5 14.5a2.5 2.5 0 0 0 2.5 2.5"/>',
    "fork": '<path d="M7 3v7"/><path d="M4.5 3v4.5a2.5 2.5 0 0 0 5 0V3"/><path d="M7 10v11"/><path d="M17 3c-2.4 2.2-2.4 7 0 9v9"/>',
    "dumbbell": '<path d="M6.5 7v10"/><path d="M17.5 7v10"/><path d="M3.5 9.5v5"/><path d="M20.5 9.5v5"/><path d="M6.5 12h11"/>',
    "calendar": '<rect x="4" y="5.5" width="16" height="15" rx="2.5"/><path d="M4 10h16"/><path d="M9 3.5v4"/><path d="M15 3.5v4"/>',
    "gauge": '<path d="M4.5 17a7.5 7.5 0 1 1 15 0"/><path d="M12 17l3.6-4.4"/>',
    "spark": '<path d="M12 3v5"/><path d="M12 16v5"/><path d="M3 12h5"/><path d="M16 12h5"/><path d="M6 6l3 3"/><path d="M15 15l3 3"/>',
    "syringe": '<path d="M17 3l4 4"/><path d="M19 5l-9.5 9.5"/><path d="M15 5l4 4"/><path d="M8 12l4 4"/><path d="M9.5 14.5L5 19"/><path d="M3 21l2-2"/>',
}
CHECK = '<svg viewBox="0 0 24 24" width="{s}" height="{s}" fill="none" stroke="{c}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path pathLength="1" d="M5 12.5l4.2 4.2L19 7"/></svg>'


def icon(name, size=40):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="#fff" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, ICONS["spark"])}</svg>')


# ---------------------------------------------------------------------------------------------- geometry
def est_size(c):
    """(w, h) estimate of a card at rest (only used for QA regions and cluster spans; `w`/`h` override)."""
    k = c.get("type", "icon")
    if k == "chip":
        w, h = 60 + len(c["text"]) * 22 + (54 if c.get("icon") else 0), 66
    elif k == "panel":
        w, h = 680, 160 + 46 * len(c.get("rows", [])) + (52 if c.get("slot") else 0)
    elif k == "status":
        w, h = 680, 330 + (70 if c.get("row") else 0)
    elif k == "week":
        w, h = 288, 196
    else:
        if c.get("hero"):
            t = max(len(c.get("title", "")) * 33.0, len(c.get("sub", "")) * 16.5)
            w, h = 26 + 106 + 28 + t + 46, 158
        else:
            t = max(len(c.get("title", "")) * 27.6, len(c.get("sub", "")) * 15.0)
            w, h = 22 + 88 + 22 + t + 38, 134
    return int(c.get("w", w)), int(c.get("h", h))


def home(c):
    w, h = est_size(c)
    x = (1080 - w) // 2 if c.get("x") == "center" else int(c["x"])
    return [x, int(c["y"]), w, h]


def side(c):
    x, _, w, _ = home(c)
    cx = x + w / 2
    return "left" if cx < 470 else ("right" if cx > 610 else "center")


def clusters(cards, windows):
    """group id per card: explicit `group`, else chained by overlapping lifetimes."""
    gid, out, cur, end = 0, [], None, -1
    for c, (f0, f1) in zip(cards, windows):
        if c.get("group") is not None:
            out.append(f"g:{c['group']}")
            continue
        if cur is None or f0 >= end:
            gid += 1
            cur = f"a{gid}"
        end = max(end, f1)
        out.append(cur)
    return out


def span(rects):
    x0 = min(r[0] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    return x0, x1 - x0


# ---------------------------------------------------------------------------------------------- html
def card_html(c, eid, t0, t1):
    kind = c.get("type", "icon")
    b = kit.box("card", t0, t1, False)
    tb = kit.box("text", t0, t1, True)
    ico_cls = "ico gold" if c.get("gold") else "ico"
    strike = f'<i class="strike" id="{eid}x"></i>' if c.get("strike_at") else ""
    if kind == "chip":
        ic = f'<span class="{ico_cls} sm">{icon(c["icon"], 26)}</span>' if c.get("icon") else ""
        inner = f'<div class="el chip" id="{eid}" {b}>{ic}<span {tb}>{esc(c["text"])}</span>{strike}</div>'
    elif kind == "panel":
        rows = []
        for j, r in enumerate(c.get("rows", [])):
            rows.append(f'<div class="fr"><span class="nm" {tb}>{esc(r[0])}</span><i><b id="{eid}b{j}" style="width:{r[1]}%"></b></i>'
                        f'<span class="tk" id="{eid}t{j}">{CHECK.format(s=30, c="currentColor")}</span></div>')
        if c.get("slot"):
            s = c["slot"]
            rows.append(f'<div class="fr slot" id="{eid}s"><span class="nm" {tb}>{esc(s["label"])}</span>'
                        f'<span class="q" id="{eid}sq">?</span><span class="tk on" id="{eid}st">{CHECK.format(s=30, c="currentColor")}</span></div>')
        inner = (f'<div class="el card panel" id="{eid}" {b}><div class="hdr"><div class="{ico_cls}">{icon(c.get("icon", "tube"))}</div>'
                 f'<div class="tx"><span class="tt" {tb}>{esc(c["title"])}</span><span class="sb" {tb}>{esc(c.get("sub", ""))}'
                 f'<i class="ul" id="{eid}u"></i></span></div></div><div class="rows">{"".join(rows)}</div>{strike}</div>')
    elif kind == "status":
        row2 = (f'<div class="row2" id="{eid}r"><span class="dot" id="{eid}d"></span><span {tb}>{esc(c["row"])}</span></div>'
                if c.get("row") else "")
        inner = (f'<div class="el card status" id="{eid}" {b}><span class="eb" {tb}>{esc(c.get("eyebrow", ""))}</span>'
                 f'<span class="big" id="{eid}v"><span class="gl" id="{eid}g"></span><span class="vv" {tb}>{esc(c["value"])}</span></span>'
                 f'<span class="unit" {tb}>{esc(c.get("unit", ""))}</span>{row2}{strike}</div>')
    elif kind == "week":
        flag = f'<span class="flag" id="{eid}f" {tb}>{esc(c["flag"])}</span>' if c.get("flag") else ""
        cls = "el card week pick" if c.get("flag") else "el card week"
        inner = (f'<div class="{cls}" id="{eid}" {b}>{flag}<span class="eb"><span class="{ico_cls}">{icon("calendar", 28)}</span>'
                 f'<span {tb}>{esc(c.get("label", "Week"))}</span></span><span class="n" {tb}>{esc(c["n"])}</span>{strike}</div>')
    else:
        mw = f' style="min-width:{int(c["w"])}px;justify-content:center"' if c.get("w") else ""
        inner = (f'<div class="el card{" hero" if c.get("hero") else ""}" id="{eid}"{mw} {b}><div class="{ico_cls}">{icon(c.get("icon", "spark"))}</div>'
                 f'<div class="tx"><span class="tt" {tb}>{esc(c["title"])}</span>'
                 + (f'<span class="sb" {tb}>{esc(c["sub"])}</span>' if c.get("sub") else "") + f'</div>{strike}</div>')
    x, y, w, _ = home(c)
    if c.get("x") == "center":
        pos = f"left:0;top:{y}px;width:1080px;display:flex;justify-content:center"
    else:
        pos = f"left:{x}px;top:{y}px"
    return (f'<div class="kw" id="{eid}w" style="{pos}"><div class="kf" id="{eid}f0">'
            f'<div class="ksh" id="{eid}h"></div>{inner}</div></div>')


# ---------------------------------------------------------------------------------------------- motion
def fly_from(c, sd, seed):
    """3D start state of the fly-in, by side (or `from`)."""
    d = c.get("from") or sd
    j = ((seed * 37) % 7 - 3) / 3.0                         # -1..1, seeded variety
    base = {"opacity": 0.55, "filter": "blur(13px)", "transformPerspective": PERSP, "scale": 0.92}
    if d == "left":
        base.update(x=-210, y=40 + 20 * j, z=-280, rotationY=62, rotationX=10, rotation=-7 + 3 * j)
    elif d == "right":
        base.update(x=210, y=40 + 20 * j, z=-280, rotationY=-62, rotationX=10, rotation=7 + 3 * j)
    elif d == "above":
        base.update(x=30 * j, y=-90, z=-240, rotationX=-50, rotation=5 * j)
    elif d == "front":
        base.update(y=70, z=420, rotationX=-28, rotation=4 * j, opacity=0.5, filter="blur(16px)")
    else:  # below / center
        base.update(x=30 * j, y=190, z=-200, rotationX=60, rotation=-4 * j)
    return base


def enter(tl, c, eid, t0, seed):
    sd = side(c)
    frm = fly_from(c, sd, seed)
    to = {"opacity": 1, "x": 0, "y": 0, "z": 0, "rotationY": 0, "rotationX": 0, "rotation": 0, "scale": 1,
          "transformPerspective": PERSP}
    sel = f"#{eid}"
    tl.set(f"{sel}w", t0, {"visibility": "visible"})
    tl.set(sel, t0, {"visibility": "visible"})
    blur = frm.pop("filter")
    # motion blur: heavy while it travels, gone a few frames before it lands (the overshoot reads sharp)
    tl.fromto(sel, t0, frm, to, LAND, "back.out(1.4)")
    tl.fromto(sel, t0, {"filter": blur}, {"filter": "blur(0px)"}, 0.2, "expo.out")
    # contact shadow: far and faint while the card is in the air, tight and dark on landing
    tl.fromto(f"{sel}h", t0, {"opacity": 0, "scale": 1.35, "y": 46}, {"opacity": 1, "scale": 1, "y": 0}, LAND, "power2.out")


def float_idle(tl, eid, t_land, t_end, seed):
    """Gentle orbit while the card holds: two sine yoyos with different periods (never in step)."""
    life = t_end - t_land
    if life < 1.0:
        return
    j = (seed * 53) % 11 / 10.0
    p1, p2 = 3.0 + 0.8 * j, 4.1 - 0.6 * j
    sgn = 1 if seed % 2 else -1
    n1, n2 = max(0, int(life / (p1 / 2)) - 1), max(0, int(life / (p2 / 2)) - 1)
    sel = f"#{eid}f0"
    tl.to(sel, t_land, {"y": -9 * sgn, "rotation": 0.7 * sgn, "repeat": n1, "yoyo": True}, p1 / 2, "sine.inOut")
    tl.to(sel, t_land, {"rotationY": 5 * sgn, "rotationX": -3 * sgn, "transformPerspective": 900, "repeat": n2,
                        "yoyo": True}, p2 / 2, "sine.inOut")


def hide(tl, eid, t):
    """Off: the wrapper goes to opacity 0 (the card itself is set visible inline, so visibility alone would not
    reach it), and the card is hidden too."""
    tl.set(f"#{eid}w", t, {"opacity": 0, "visibility": "hidden"})
    tl.set(f"#{eid}", t, {"visibility": "hidden"})


def move(tl, eid, t, m, dur=0.46):
    v = {"x": m.get("dx", 0), "y": m.get("dy", 0), "rotation": m.get("rot", 0), "scale": m.get("scale", 1),
         "rotationY": m.get("ry", 0), "transformPerspective": PERSP}
    if "o" in m:
        v["opacity"] = m["o"]
    if "blur" in m:
        v["filter"] = f"blur({m['blur']}px)"
    tl.to(f"#{eid}w", t, v, m.get("dur", dur), m.get("ease", "expo.out"))


def exit_fly(tl, c, eid, t1, d=0.22):
    s = {"left": -1, "right": 1}.get(side(c), 0)
    tl.to(f"#{eid}", t1 - d, {"x": 150 * s, "y": -30 if s == 0 else 0, "z": -650, "rotationY": 55 * (s or 1),
                              "opacity": 0, "filter": "blur(9px)", "transformPerspective": PERSP}, d, "power3.in")
    tl.to(f"#{eid}h", t1 - d, {"opacity": 0}, d, "power3.in")
    hide(tl, eid, t1)


def strike_tumble(tl, c, eid, ts, last):
    """The red strike draws through the card, then the card lifts, tips and falls out AWAY from the face."""
    s = {"left": -1, "right": 1}.get(side(c), 1)
    tl.fromto(f"#{eid}x", ts, {"scaleX": 0, "rotation": -5, "opacity": 1}, {"scaleX": 1, "rotation": -5}, 0.14, "power2.inOut")
    t = ts + 0.18
    lx, ly = last.get("dx", 0), last.get("dy", 0)
    tl.to(f"#{eid}w", t, {"y": ly - 34, "rotation": 6 * s, "transformPerspective": PERSP}, 0.1, "power2.out")
    tl.to(f"#{eid}w", t + 0.1, {"x": lx + 470 * s}, 0.5, "power2.out")
    tl.to(f"#{eid}w", t + 0.1, {"y": ly + 1350, "rotation": 34 * s, "rotationX": 38}, 0.6, "power2.in")
    hide(tl, eid, t + 0.72)
    return t + 0.72
