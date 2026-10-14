"""Hook inserts for MOTION EDITORIAL (deterministic HTML + GSAP, used on `media` beats and as overlays).

  media_stack  full-frame media plate: one full-bleed clip, or a top panel + a bottom panel (clip or dark), a seam
               hairline, tiny corner labels. Clips pan on a source-y track (cut-time keyframes, so a track continues
               across beats), the bottom panel can slide in on a word, the full clip can shake on a hit.
  title_card   the hook title (2 ALL-CAPS lines) on a paper card that slams in on a hit and leaves before a cut.
"""
import json

from ctx import esc, floor5, snap

PANEL_H = 960


def _pan_y(pan, t):
    """pan: [[cut_t, src_y], ...] -> window top (source px) at cut time t, linear between keyframes."""
    if not pan:
        return 0.0
    if t <= pan[0][0]:
        return float(pan[0][1])
    for (ta, ya), (tb, yb) in zip(pan, pan[1:]):
        if t <= tb:
            return ya + (yb - ya) * (t - ta) / max(tb - ta, 1e-6)
    return float(pan[-1][1])


def _pan_tweens(cx, sel, pan, t0, t1):
    cx.set(sel, t0, {"y": -round(_pan_y(pan, t0), 1)})
    marks = sorted({t0, t1} | {k[0] for k in (pan or []) if t0 < k[0] < t1})
    keys = [f'{{y:{-_pan_y(pan, b):.1f},duration:{b - a:.3f},ease:"none"}}' for a, b in zip(marks, marks[1:])]
    if any(abs(_pan_y(pan, m) - _pan_y(pan, t0)) > 0.5 for m in marks):   # one tween, keyframed: no overlaps
        cx.tw.append(f'tl.to({json.dumps(sel)},{{keyframes:[{",".join(keys)}]}},{snap(t0)});')


def _clip(cx, beat, spec, box, t_from):
    """One clip in a clipping box. spec: {src, track_t0 | media_start, pan [[cut_t, src_y]], scale, steps, h}.
    track_t0: the clip is a cut-time track that starts at that cut time (continues across beats).
    steps: [[anchor, scale, ox, oy, push_to?, push_dur?]] hard framing changes on words or cut frames ("#seg"),
           optionally followed by a slow push."""
    cx.check_asset(spec["src"])
    x, y, w, h = box
    t0, t1 = max(beat["t0"], t_from), beat["t1"]
    ms = (t0 - spec["track_t0"]) if "track_t0" in spec else float(spec.get("media_start", 0.0)) + (t0 - beat["t0"])
    total = cx.media_dur(spec["src"])
    length = t1 - t0
    if total is not None and ms + length > total + 0.03:
        cx.warn(f"clip {spec['src']} is {total:.2f}s but beat {beat['id']} needs {ms + length:.2f}s; it ends early")
        length = max(total - ms, 0.1)
    wid, pid, vid = cx.uid("mw"), cx.uid("mp"), cx.uid("mv")
    sc = float(spec.get("scale", 1.0))
    if abs(sc - 1) > 1e-3:   # closer framing of the same clip (origin top centre; pan stays in source px)
        cx.init.append(f'gsap.set("#{pid}",{{scale:{sc},transformOrigin:"540px 0px"}});')
    _pan_tweens(cx, f"#{pid}", [[t, y * sc] for t, y in (spec.get("pan") or [])], t0, t1)
    for st in spec.get("steps", []):   # hard framing steps: [anchor, scale, origin_x, origin_y, (push_to, push_dur)]
        ts = cx.when(st[0], beat)
        cx.set(f"#{pid}", ts, {"scale": st[1], "transformOrigin": f"{st[2]}px {st[3]}px"})
        if len(st) > 4:          # then a slow push from that framing
            cx.to(f"#{pid}", ts + 1 / 30, {"scale": st[4]}, dur=st[5] if len(st) > 5 else 0.6, ease="sine.out")
        if any(abs(ts - sg["t0"]) < 0.02 for sg in getattr(cx, "segs", [])):
            cx.cut_change(ts)
    vh = spec.get("h", 1920)
    attrs = (f'data-start="{floor5(t0)}" data-media-start="{floor5(ms)}" data-duration="{floor5(length)}" '
             f'data-track-index="{cx.next_track()}"')
    html = (f'<div class="mwrap" id="{wid}" data-layout-allow-overflow style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" '
            f'{cx.box("video", t0, t1)}><div class="mpan" id="{pid}" data-layout-allow-overflow style="height:{vh}px">'
            f'<video id="{vid}" class="mvid" src="{esc(spec["src"])}" muted playsinline {attrs} '
            f'style="height:{vh}px"></video></div></div>')
    return html, wid


def shake(cx, sel, t, amp=14, dur=0.32, seed=3):
    """Deterministic decaying camera shake (x/y jolts), ends at rest."""
    pts = [(1, -0.6), (-0.8, 0.9), (0.6, -0.4), (-0.4, 0.5), (0.2, -0.2), (0, 0)]
    step = dur / len(pts)
    for i, (kx, ky) in enumerate(pts):
        k = amp * (1 - i / len(pts))
        cx.tw.append(f'tl.to({json.dumps(sel)},{{x:{kx * k:.1f},y:{ky * k:.1f},duration:{step:.3f},ease:"power1.inOut"}},'
                     f'{snap(t) + i * step:.4f});')


def _label(cx, beat, text, x, y, t):
    lid = cx.uid("ml")
    cx.enter(beat, f"#{lid}", t, {"opacity": 0, "x": -16}, dur=0.28)
    return (f'<div class="mlab" id="{lid}" style="left:{x}px;top:{y}px" {cx.box("text", max(t, beat["t0"]), beat["t1"], True)}>'
            f'{esc(text)}</div>')


def media_stack(cx, beat, a):
    """args: full {src, media_start|track_t0, pan, push, shake_at} | top {...} + bottom {...}|"dark",
    bottom.slide_at (anchor: slides up from a visible state), labels [{text, panel: top|bottom, at}], seam, cap_y."""
    t0, t1 = beat["t0"], beat["t1"]
    parts = ['<div class="mbg"></div>']
    if a.get("full"):
        f = a["full"]
        html, wid = _clip(cx, beat, f, [0, 0, 1080, 1920], t0)
        parts.append(html)
        if f.get("push"):
            p0, p1 = f["push"]
            cx.tw.append(f'tl.fromTo("#{wid}",{{scale:{p0}}},{{scale:{p1},duration:{t1 - t0:.3f},ease:"none"}},{snap(t0)});')
        if f.get("shake_at") is not None:
            shake(cx, f"#{wid} .mpan", cx.when(f["shake_at"], beat), f.get("shake_amp", 16))
    else:
        top, bot = a["top"], a.get("bottom", "dark")
        thtml, twid = _clip(cx, beat, top, [0, 0, 1080, PANEL_H], t0)
        parts.append(thtml)
        sid = cx.uid("ms")
        if isinstance(bot, dict):
            ts = cx.when(bot.get("slide_at"), beat) if bot.get("slide_at") is not None else t0
            html, wid = _clip(cx, beat, bot, [0, PANEL_H, 1080, PANEL_H], t0)
            parts.append(html)
            if bot.get("slide_at") is not None:  # starts mostly in: the cut frame already shows the new panel
                sf, dur = bot.get("slide_from", 150), bot.get("slide_dur", 0.34)
                for sel in (f"#{wid}", f"#{sid}"):
                    cx.enter(beat, sel, ts, {"y": sf}, {"y": 0}, dur=dur, ease=bot.get("slide_ease", "power3.out"))
                if bot.get("shrink_top"):   # the full-frame shot above compresses into the top half as it rises
                    cx.enter(beat, f"#{twid}", ts, {"height": PANEL_H + sf}, {"height": PANEL_H}, dur=dur,
                             ease=bot.get("slide_ease", "power3.out"))
                cx.event(ts, "whoosh", "bottom panel slides in")
        else:
            parts.append('<div class="mdark"></div>')
        if a.get("seam", True):
            parts.append(f'<div class="mseam" id="{sid}"></div>')
    for lb in a.get("labels", []):
        y = 246 if lb.get("panel", "top") == "top" else PANEL_H + 26
        parts.append(_label(cx, beat, lb["text"], lb.get("x", 50), y, cx.when(lb.get("at"), beat, 0.15)))
    return f'<div class="mstack">{"".join(parts)}</div>'


def title_card(cx, beat, a):
    """The hook title on a paper card. args: l1, l2 (default project hook), y, enter: slam|cut, exit (s before end)."""
    l1 = a.get("l1") or cx.hook.get("l1", "")
    l2 = a.get("l2") or cx.hook.get("l2", "")
    tid, t0, t1 = cx.uid("tc"), beat["t0"], beat["t1"]
    if a.get("enter", "slam") == "slam":
        cx.enter(beat, f"#{tid}", t0, {"opacity": 0.0, "scale": 1.38}, {"opacity": 1, "scale": 1}, dur=0.3,
                 ease="back.out(1.7)")
        cx.event(t0, "thud", "hook title")
    ex = a.get("exit", 0.16)
    if ex:
        cx.to(f"#{tid}", t1 - ex, {"opacity": 0, "y": -26}, dur=ex - 0.02, ease="power2.in")
    mx = a.get("max", 900)
    return (f'<div class="centerrow" style="top:{a.get("y", 236)}px"><div class="tcard" id="{tid}" {cx.box("card", t0, t1)}>'
            f'<span class="tl tl1" data-fitgroup="{tid}" data-fitmax="{mx}" {cx.box("text", t0, t1, True)}>{esc(l1)}</span>'
            f'<span class="tl tl2" data-fitgroup="{tid}" data-fitmax="{mx}" {cx.box("text", t0, t1, True)}>{esc(l2)}</span>'
            f'</div></div>')


def css(brand):
    c = brand["colors"]
    return f"""
/* hook: media plate */
.mstack{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.mbg{{position:absolute;inset:0;background:radial-gradient(120% 70% at 50% 40%,#17141a 0%,{c['ink']} 70%)}}
.mdark{{position:absolute;left:0;top:{PANEL_H}px;width:1080px;height:{PANEL_H}px;
  background:radial-gradient(90% 60% at 50% 35%,#1b171c 0%,{c['ink']} 75%)}}
.mwrap{{position:absolute;overflow:hidden;transform-origin:50% 50%}}
.mpan{{position:absolute;left:0;top:0;width:1080px}}
.mvid{{position:absolute;left:0;top:0;width:1080px;object-fit:cover}}
.mseam{{position:absolute;left:0;top:{PANEL_H - 2}px;width:1080px;height:4px;background:{c['bg']};opacity:.9}}
.mlab{{position:absolute;font:700 30px/1 var(--fm);letter-spacing:.2em;text-transform:uppercase;color:{c['bg']};
  background:{c['accent']};padding:12px 16px 11px;border-radius:8px;white-space:nowrap;box-shadow:0 8px 22px rgba(0,0,0,.35)}}
/* hook title card */
.tcard{{display:inline-block;background:{c['bg']};border-radius:28px;text-align:center;padding:30px 44px 34px;
  box-shadow:0 30px 70px rgba(0,0,0,.45),0 6px 18px rgba(0,0,0,.25);transform-origin:50% 50%}}
.tl{{display:block;width:max-content;margin:0 auto;white-space:nowrap;font:900 100px/1.0 var(--fd);letter-spacing:-.03em;word-spacing:.07em;
  text-transform:uppercase}}
.tl1{{color:{c['ink']}}}
.tl2{{color:{c['accent']};margin-top:4px}}
"""
