"""deskmotion.py: Desk Demo Motion v2 phase 3 (handheld screen cutaways, whips, spotlight, phone frame).

All camera-like moves are planned here in Python and applied per frame (RRM.keys: one tl.set per changed frame, so
every frame is deterministic and seek-safe). Needs the motion layer (RRM) loaded: compose only calls this when
project.json "motion" is not false.

  handheld(...)      phone-at-the-monitor camera for one screen shot: shake + slow drift + a push toward each clicked
                     UI point that lands on the click, released a little after
  whip_rows(...)     the screen shot whips in on its first frames and out on its last (directional motion blur)
  scroll_blur(...)   vertical motion blur that follows a scroll's speed
  focus_pull(...)    the phone camera hunts focus on the shot's first frames
  phone(...)         the speaker shrinks into a phone frame (style_cfg "phone"), labels land on words, back on the cut
"""
import json
import math
import random

FPS = 30
CAM_O = (540.0, 900.0)       # .cam transform-origin
T_O = (540.0, 860.0)         # #mvT transform-origin (engine T_ORIGIN)
AIM = (540.0, 820.0)         # where a clicked point drifts toward
WHIP_IN, WHIP_OUT = 7, 4


def _eio(p):
    p = min(1.0, max(0.0, p))
    return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2


def _eout(p, n=3):
    return 1 - (1 - min(1.0, max(0.0, p))) ** n


def keys(sel, fields, rows, filt=None):
    opt = f",{{filter:{json.dumps(filt)}}}" if filt else ""
    return f"RRM.keys(tl,{json.dumps(sel)},{json.dumps(fields)}," + json.dumps(rows, separators=(",", ":")) + opt + ");"


def filters_html(ids):
    """One SVG blur filter per id (its feGaussianBlur is `<id>g`, keyed by RRM.keys)."""
    f = "".join(f'<filter id="{i}" x="-8%" y="-8%" width="116%" height="116%" color-interpolation-filters="sRGB">'
                f'<feGaussianBlur id="{i}g" in="SourceGraphic" stdDeviation="0 0"/></filter>' for i in ids)
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{f}</svg>'


def to_frame(c, px, py):
    """Screen point (CSS px on the monitor) -> frame point, from the shot's monitor placement (tilt ignored)."""
    fx, fy = c["focus"]
    tx, ty = c["_at"]
    return tx + (px - fx) * c["s"], ty + (py - fy) * c["s"]


def handheld(n, seed, amp, push, aims, bottom=None, limit=1340.0):
    """Per-frame [x, y, rotation, scale] for the .cam of one shot.
    aims: [(frame offset of the click, frame x, frame y, k)]. The camera eases toward each point over 0.75 s, lands on
    the click, then gives back 40 % over the next second (a person re-steadies the phone)."""
    rnd = random.Random(seed)
    ph = [rnd.random() * 6.283 for _ in range(12)]
    drift = (rnd.choice([-1, 1]) * (34 + 16 * rnd.random()), rnd.choice([-1, 1]) * (14 + 10 * rnd.random()))
    rows = []
    for i in range(n):
        t = i / FPS
        x = amp * (4.2 * math.sin(6.283 * 0.53 * t + ph[0]) + 2.0 * math.sin(6.283 * 1.7 * t + ph[1])
                   + 0.8 * math.sin(6.283 * 4.3 * t + ph[2]))
        y = amp * (3.6 * math.sin(6.283 * 0.47 * t + ph[3]) + 1.7 * math.sin(6.283 * 1.9 * t + ph[4])
                   + 0.8 * math.sin(6.283 * 3.9 * t + ph[5]))
        r = amp * (0.3 * math.sin(6.283 * 0.39 * t + ph[6]) + 0.1 * math.sin(6.283 * 1.3 * t + ph[7]))
        p = i / max(1, n - 1)
        x += drift[0] * (p - 0.5)
        y += drift[1] * (p - 0.5)
        s, tx, ty = 1.0 + push * p, 0.0, 0.0
        for fo, px, py, k in aims:
            a = _eio((i - (fo - 22)) / 22.0) - 0.4 * _eio((i - (fo + 8)) / 30.0)
            if a <= 0:
                continue
            kk = 1 + (k - 1) * a
            want_x, want_y = px + 0.45 * (AIM[0] - px), py + 0.45 * (AIM[1] - py)
            tx += a * (want_x - CAM_O[0] - k * (px - CAM_O[0]))
            ty += a * (want_y - CAM_O[1] - k * (py - CAM_O[1]))
            s *= kk
        yy = y + ty
        if bottom is not None:     # the screen never slides down into the caption band
            yy = min(yy, limit - CAM_O[1] - s * (bottom - CAM_O[1]))
        rows.append([round(x + tx, 2), round(yy, 2), round(r, 3), round(s, 4)])
    return rows


def whip_rows(f0, f1, k, enter_dir, leave_dir):
    """#s<k> (the whole cutaway) rows [f, x, scale, bx, by]: whip in on the first frames, out on the last."""
    rows = []
    if enter_dir:
        for j in range(WHIP_IN):
            p = _eout(j / WHIP_IN, 3)
            rows.append([f0 + j, round(enter_dir * 260 * (1 - p), 1), 1, round(40 * (1 - p), 1), 0])
        rows.append([f0 + WHIP_IN, 0, 1, 0, 0])
    if leave_dir:
        for j in range(WHIP_OUT):
            p = ((j + 1) / WHIP_OUT) ** 2
            rows.append([f1 - WHIP_OUT + j, round(leave_dir * 240 * p, 1), 1, round(44 * p, 1), 0])
        rows.append([f1, 0, 1, 0, 0])
    return rows


def scroll_blur(f0, dur, peak=7.0):
    """[f, bx, by] rows: vertical blur that follows a power2.inOut scroll's speed."""
    n = max(2, int(round(dur * FPS)))
    rows = [[f0 + i, 0, round(peak * math.sin(math.pi * i / n) ** 1.5, 2)] for i in range(n)]
    return rows + [[f0 + n, 0, 0]]


def focus_pull(tl, sel, t0, base="contrast(0.93) brightness(1.03) saturate(0.94)"):
    """The phone camera hunts focus: soft -> sharp -> a touch soft -> sharp, in 0.6 s."""
    soft, sharp, mid = f"{base} blur(6px)", f"{base} blur(0.35px)", f"{base} blur(1.8px)"
    tl.fromto(sel, t0, {"filter": soft}, {"filter": sharp}, 0.22, "power2.out")
    tl.fromto(sel, t0 + 0.27, {"filter": sharp}, {"filter": mid}, 0.08, "sine.inOut")
    tl.fromto(sel, t0 + 0.4, {"filter": mid}, {"filter": sharp}, 0.2, "power2.out")


# ---------------------------------------------------------------------------------------------- phone frame
PHONE_CSS = """
#ddBack{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:0;background:#141210;overflow:hidden;opacity:0;visibility:hidden}
#ddBack .room{position:absolute;inset:-60px;background-size:cover;background-position:center;filter:blur(30px) brightness(.42) saturate(.8)}
#ddBezel{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:3;pointer-events:none;transform-origin:540px 860px;
  border:22px solid #0d0d10;border-radius:96px;box-shadow:inset 0 0 0 3px #2a2a30,0 0 0 4px #26262b;opacity:0;visibility:hidden}
#ddBezel i{position:absolute;left:400px;top:26px;width:236px;height:62px;border-radius:40px;background:#0d0d10}
.ddlab{position:absolute;z-index:25;opacity:0;visibility:hidden;white-space:nowrap}
.ddlab span{display:inline-block;font:900 64px/1 var(--fd);letter-spacing:-.02em;word-spacing:.06em;color:#fff;background:var(--acc);padding:16px 28px 18px;
  border-radius:20px;box-shadow:0 18px 40px rgba(0,0,0,.35)}
.ddlab.soft span{font:800 46px/1 var(--fb);background:#fff;color:#111;padding:14px 24px 16px;border-radius:999px}
"""


def phone(proj, tl, cfg, resolve, frame_of, box):
    """style_cfg "phone": {"from": "seg:n1d", "to": "seg:n1e", "in": "@insulin"|seconds, "scale": 0.66, "top": 250,
    "labels": [{"text": "OVER 7", "at": "@seven", "x": 610, "y": 330, "rot": -5, "kind": "stamp"|"soft"}]}
    -> (html, js, (f_in, f_out)). The speaker layer (#mvT) shrinks into a phone over a dark blurred room and comes back
    full frame on the `to` cut (its own move: the engine transition on that cut is switched off)."""
    pc = cfg.get("phone")
    if not pc:
        return "", [], None
    f_from, f_to = resolve(proj, pc["from"]), resolve(proj, pc["to"])
    t_in = proj.at(pc["in"], f_from / FPS) - 0.05 if isinstance(pc.get("in"), str) else f_from / FPS + float(pc.get("in", 0.25))
    fi = max(f_from + 7, frame_of(t_in))
    s_ph, top = float(pc.get("scale", 0.66)), float(pc.get("top", 250))
    ty_ph = top - T_O[1] * (1 - s_ph)
    rows, bez = [], []
    n_in, n_out = 14, 7
    for f in range(fi, f_to + n_out + 1):
        if f < fi + n_in:
            p = _eout((f - fi + 1) / n_in, 4)
        elif f < f_to:
            p = 1.0
        else:
            q = (f - f_to) / n_out
            p = 1 - _eout(q, 3)
        s = 1 + (s_ph - 1) * p
        if f >= f_to and f < f_to + n_out:
            s *= 1 + 0.06 * math.sin(math.pi * (f - f_to) / n_out)      # lands a touch past full: a crisp return
        rad = round(96 * p)
        clip = f"inset(0px 0px 0px 0px round {rad}px)" if rad > 0 else "none"
        rows.append([f, round(s, 4), 0, round(ty_ph * p, 1), clip])
        bez.append([f, round(s, 4), 0, round(ty_ph * p, 1), round(min(1.0, p * 1.4), 3)])
    js = [keys("#mvT", ["scale", "x", "y", "clipPath"], rows), keys("#ddBezel", ["scale", "x", "y", "o"], bez)]
    tl.set("#ddBack", fi / FPS, {"opacity": 1, "visibility": "visible"})
    tl.set("#ddBack", (f_to + n_out) / FPS, {"opacity": 0, "visibility": "hidden"})
    tl.event(fi / FPS, "enter", "speaker shrinks into the phone", region=[0, 0, 1080, 1920])
    tl.event(f_to / FPS, "enter", "back to full frame", region=[0, 0, 1080, 1920])
    tl.cue(fi / FPS, "swish", -3)
    html = ['<div id="ddBezel"><i></i></div>']
    for j, lab in enumerate(pc.get("labels", [])):
        lid = f"ddl{j}"
        t = max(fi / FPS + 0.2, proj.at(lab["at"], f_from / FPS) - 0.04)
        t_end = f_to / FPS
        kind = lab.get("kind", "stamp")
        html.append(f'<div class="ddlab {"soft" if kind == "soft" else ""}" id="{lid}" style="left:{lab["x"]}px;top:{lab["y"]}px;'
                    f'transform:rotate({lab.get("rot", 0)}deg)"><span {box("card", t, t_end, True)}>{lab["text"]}</span></div>')
        tl.set(f"#{lid}", t, {"visibility": "visible"})
        if kind == "stamp":
            tl.fromto(f"#{lid}", t, {"opacity": 0.7, "scale": 2.0, "filter": "blur(14px)"},
                      {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, 0.22, "power4.out")
            tl.cue(t, "thump", -2)
        else:
            tl.fromto(f"#{lid}", t, {"opacity": 0.7, "y": 30, "scale": 0.9, "filter": "blur(10px)"},
                      {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, 0.36, "back.out(1.6)")
            tl.cue(t, "pop", -2)
        tl.set(f"#{lid}", t_end, {"opacity": 0, "visibility": "hidden"})
        tl.event(t, "enter", f"label {lab['text']}", region=[140, lab["y"], 800, 140])   # label over the phone: the phone is the hero
    return "\n".join(html), js, (fi, f_to)


# ---------------------------------------------------------------------------------------------- native checklist
NOTES_CSS = """
.ddn{position:absolute;left:150px;width:780px;z-index:24;background:#fff;border-radius:36px;padding:26px 34px 24px;
  box-shadow:0 22px 60px rgba(0,0,0,.28),0 4px 14px rgba(0,0,0,.12);opacity:0;visibility:hidden;font-family:var(--fb)}
.ddn h3{margin:0 0 10px;font:800 40px/1.1 var(--fd);color:#111;letter-spacing:-.02em;word-spacing:.04em;display:flex;align-items:center;gap:14px}
.ddn h3 b{margin-left:auto;font:800 30px/1 var(--fb);color:var(--acc)}
.ddn .r{position:relative;display:flex;align-items:center;gap:20px;height:54px;font:700 38px/1 var(--fb);color:#9aa0a8;white-space:nowrap}
.ddn .c{position:relative;width:42px;height:42px;border-radius:50%;border:3.5px solid #c9ced6;flex:none}
.ddn .c i{position:absolute;inset:-3.5px;border-radius:50%;background:var(--acc);opacity:0;display:flex;align-items:center;justify-content:center}
.ddn .c i svg{width:26px;height:26px}
"""
TICK = ('<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#fff" stroke-width="3.4" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def notes(proj, tl, cfg, resolve, frame_of, box, esc):
    """style_cfg "notes": a phone-native checklist over the face segment that ticks on the words.
    {"from": "seg:cred2", "to": "@thing", "title": "Who is talking", "y": 236, "items": [{"text", "at"}]}"""
    nc = cfg.get("notes")
    if not nc:
        return ""
    f0 = resolve(proj, nc["from"])
    t0 = f0 / FPS
    t_end = proj.at(nc["to"], t0) if isinstance(nc["to"], str) and nc["to"].startswith("@") else resolve(proj, nc["to"]) / FPS
    y, n = int(nc.get("y", 236)), len(nc["items"])
    h = 74 + n * 54 + 24
    tl.set("#ddn", t0, {"visibility": "visible"})
    tl.fromto("#ddn", t0, {"opacity": 0.75, "y": -40, "scale": 0.96, "filter": "blur(8px)"},
              {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, 0.4, "expo.out")
    tl.event(t0, "enter", "notes card", region=[150, y, 780, h])
    tl.cue(t0, "swish", -4)
    rows = []
    for i, it in enumerate(nc["items"]):
        t = max(t0 + 0.15, proj.at(it["at"], t0 - 0.05) - 0.04)
        tl.set(f"#ddn{i}", t, {"color": "#111"})
        tl.fromto(f"#ddn{i}c", t, {"opacity": 1, "scale": 0.55}, {"opacity": 1, "scale": 1}, 0.3, "back.out(2.2)")
        tl.fromto(f"#ddnk", t, {"y": -i * 40}, {"y": -(i + 1) * 40}, 0.36, "expo.out")
        tl.event(t, "enter", f"tick {it['text']}", region=[150, y + 74 + i * 54, 780, 54])
        if i % 2 == 0:
            tl.cue(t, "click", -6)
        rows.append(f'<div class="r" id="ddn{i}"><div class="c"><i id="ddn{i}c">{TICK}</i></div>'
                    f'<span {box("text", t0, t_end, True)}>{esc(it["text"])}</span></div>')
    count = "".join(f"<span style='display:block;height:40px'>{k}</span>" for k in range(n + 1))
    tl.fromto("#ddn", t_end, {"opacity": 1, "y": 0, "filter": "blur(0px)"}, {"opacity": 0, "y": -140, "filter": "blur(10px)"},
              0.22, "power3.in")
    tl.set("#ddn", t_end + 0.23, {"visibility": "hidden"})
    return (f'<div class="ddn" id="ddn" style="top:{y}px" {box("card", t0, t_end, False)}>'
            f'<h3><span {box("text", t0, t_end, True)}>{esc(nc.get("title", ""))}</span><b><span style="display:inline-block;'
            f'height:40px;overflow:hidden;vertical-align:top"><span id="ddnk" style="display:block">{count}</span></span>/{n}</b></h3>'
            f'{"".join(rows)}</div>')
