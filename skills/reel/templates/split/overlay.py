"""Full-frame overlay layer: titles, lists and cards placed in the free band ABOVE the speaker's head.

Any insert used on a `full` segment (edl `top`) or in project.json `overlays` gets `_area = (220, head_top - margin)`:
head_top is the highest point of the head box (cap/hair) on screen over the item's time range, from the per-frame
face track (work/facetrack.json) mapped through the speaker placement (punch-ins included). So an overlay can never
reach the face, whatever the framing.

Inserts here (fn(cx, beat, args) -> html):
  name_card  credential card: name + role (role lands on its word)          args: name, role, role_at, kicker, align
  chip       small pill with an optional tick, lands on a word               args: text, at, tick, tone (accent|ink|gold)
"""
from ctx import esc

TICK = ('<svg viewBox="0 0 24 24" width="30" height="30"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" '
        'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def band(a, height, align="bottom", gap=0):
    """Top y for a block in the overlay band: bottom-aligned just above the head (default) or centred."""
    y0, y1 = a.get("_area", (220, 760))
    if "y" in a:
        return a["y"]
    if align == "center":
        return round(y0 + (y1 - y0 - height) / 2)
    if align == "top":
        return y0 + gap
    return round(max(y0, y1 - height - gap))


def name_card(cx, beat, a):
    nid, t0, t1 = cx.uid("nc"), beat["t0"], beat["t1"]
    h = 200 if a.get("kicker") else 160
    top = band(a, h, a.get("align", "center"))
    at = cx.when(a.get("at"), beat, 0.0)
    cx.enter(beat, f"#{nid}", at, {"opacity": 0.55, "y": 18}, dur=0.34)
    role = ""
    if a.get("role"):
        rt = cx.when(a.get("role_at"), beat, 0.25)
        cx.enter(beat, f"#{nid}r", rt, {"opacity": 0, "x": -18}, dur=0.3)
        cx.event(rt, "click", "name card role")
        role = f'<div class="ncr" id="{nid}r" {cx.box("text", max(rt, t0), t1, True)}>{esc(a["role"])}</div>'
    kick = f'<div class="nck" {cx.box("text", t0, t1, True)}>{esc(a["kicker"])}</div>' if a.get("kicker") else ""
    return (f'<div class="centerrow" style="top:{top}px"><div class="namecard" id="{nid}" {cx.box("card", t0, t1)}>'
            f'<div class="ncbar"></div><div>{kick}<div class="ncn" data-fit="760,34" {cx.box("text", t0, t1, True)}>'
            f'{esc(a.get("name") or cx.brand.get("name", ""))}</div>{role}</div></div></div>')


def chip(cx, beat, a):
    cid, t0, t1 = cx.uid("ch"), beat["t0"], beat["t1"]
    top = band(a, 84, a.get("align", "bottom"))
    at = cx.when(a.get("at"), beat, 0.0)
    cx.enter(beat, f"#{cid}", at, {"opacity": 0, "y": 18, "scale": 0.94}, {"opacity": 1, "y": 0, "scale": 1}, dur=0.3,
             ease="back.out(1.6)")
    cx.event(at, "pop", f"chip {a.get('text')}")
    tick = f'<span class="cht">{TICK}</span>' if a.get("tick") else ""
    return (f'<div class="centerrow" style="top:{top}px"><div class="chipx {a.get("tone", "ink")}" id="{cid}" '
            f'{cx.box("text", max(at, t0), t1, True)}>{tick}{esc(a["text"])}</div></div>')


CSS = """
.namecard{display:flex;align-items:center;gap:26px;background:rgba(255,255,255,.94);border-radius:30px;padding:26px 44px 28px 30px;
  box-shadow:0 24px 60px rgba(0,0,0,.20),0 4px 14px rgba(0,0,0,.08)}
.namecard .ncbar{width:10px;align-self:stretch;border-radius:6px;background:var(--accent)}
.namecard .nck{font:700 25px/1 var(--fb);letter-spacing:.2em;text-transform:uppercase;color:var(--soft);margin-bottom:12px}
.namecard .ncn{font:800 66px/1.04 var(--fd);letter-spacing:-.02em;color:var(--ink);white-space:nowrap}
.namecard .ncr{font:700 44px/1.1 var(--fb);color:var(--accent);margin-top:10px;white-space:nowrap}
.chipx{display:inline-flex;align-items:center;gap:14px;height:84px;padding:0 36px 0 30px;border-radius:999px;white-space:nowrap;
  font:800 42px/1 var(--fd);letter-spacing:-.015em;box-shadow:0 18px 44px rgba(0,0,0,.22)}
.chipx.ink{background:rgba(255,255,255,.95);color:var(--ink)}
.chipx.accent{background:var(--accent);color:#fff}
.chipx.gold{background:var(--hl);color:var(--ink)}
.chipx .cht{display:inline-flex;width:46px;height:46px;border-radius:50%;background:var(--accent);color:#fff;align-items:center;justify-content:center}
.chipx.accent .cht{background:#fff;color:var(--accent)}
"""
