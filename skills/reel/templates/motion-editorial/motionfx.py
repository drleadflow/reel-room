"""motionfx.py: the Motion v2 craft layer of MOTION EDITORIAL ("a magazine in motion").

Two parts:
  1. Entrances and secondary motion for the inserts in style.py, on the engine runtime (RRM, engine/motion/motion.js):
     headlines rise letter by letter out of a mask or stamp in, labels track in, graphics land with blur + scale +
     offset, strokes draw on. Every element is hidden until its word (`gsap.set` at build time), never on frame 1 of the
     reel (frame 1 reads at full strength), never re-animated when a beat resumes after a cut-in.
  2. stage(): the stage rig, called by split/compose.py before the motion plan is built:
       - a camera on every graphic beat (#<beat id>): settle on the cut, a slow push through the beat, focus steps
         toward the element that just landed (inserts register them with focus()), a small seeded drift; a stage whip
         (graphic out left, next graphic in from the right, blurred) when the graphic changes inside a shot
       - the rounded speaker card as its own depth layer (#sp + #cardsh): it rises in when a card section starts,
         sinks out before a graphics-only beat, and counter-moves against the stage camera (parallax)
     All of it is keyed per frame (RRM.keys), so it is deterministic and seek-safe.
Ease names are the engine tokens (RRM.EASE values), never raw curves.
"""
import json
import math

FPS = 30
# RRM.EASE token values (engine/motion/motion.js): write these, ease_lint knows them
E = {"snap": "expo.out", "glide": "power4.out", "land": "back.out(1.4)", "pop": "back.out(2.2)", "stamp": "power4.out",
     "drift": "sine.inOut", "camera": "power2.inOut", "settle": "power2.out", "whip": "expo.inOut", "draw": "power2.inOut",
     "exit": "power3.in", "fall": "power2.in", "wobble": "elastic.out(1,0.45)"}
# how long each RRM entrance moves (s), for the stage rig's motion map
DUR = {"letters": 0.75, "letterStamp": 0.6, "stamp": 0.24, "trackIn": 0.26, "blurIn": 0.42, "pop": 0.34, "rise": 0.36,
       "smear": 0.16, "drop": 0.56, "maskPush": 0.32, "drawOn": 0.5, "wipe": 0.34, "grow": 0.34}


def _js(v):
    return json.dumps(v, separators=(",", ":"))


def _store(cx, name, beat):
    return cx.__dict__.setdefault(name, {}).setdefault(beat["id"], [])


def focus(cx, beat, t, y=None, k=1.0):
    """Ask the stage camera to step toward screen height y (px) at time t (a hero element just landed there)."""
    _store(cx, "_me_focus", beat).append((float(t), y, float(k)))


def moving(cx, beat, t0, t1):
    _store(cx, "_me_moves", beat).append((float(t0), float(t1)))


def live(cx, beat, t):
    """False when the element must show its settled state: the beat resumes after a cut-in, or t is the reel's
    very first frame (a thumbnail must read)."""
    return t >= beat["t0"] - 1e-3 and t >= 1.0 / FPS


def preroll(beat, t):
    """An entrance that starts exactly on its beat's first frame (a cut) starts 2 frames early instead, while the beat is
    still hidden: the cut lands on a graphic already in motion, never on an empty panel."""
    if beat["t0"] > 0.05 and abs(t - beat["t0"]) < 0.045:
        return beat["t0"] - 2.0 / FPS
    return t


def hide(cx, sel):
    cx.init.append(f"gsap.set({_js(sel)},{{autoAlpha:0}});")


def enter(cx, beat, sel, t, kind="blurIn", **o):
    """An RRM entrance (rise, blurIn, pop, stamp, trackIn, wipe, drawOn, smear, drop, maskPush, letters, letterStamp,
    grow) on `sel`, hidden until t. Returns the time the element has landed."""
    if not live(cx, beat, t):
        return t
    hide(cx, sel)
    t = preroll(beat, t)
    cx.tw.append(f"RRM.enter({_js(kind)},tl,document.querySelector({_js(sel)}),{t:.4f},{_js(o)});")
    d = o.get("dur", DUR.get(kind, 0.4))
    if kind in ("letters", "letterStamp"):
        d = DUR[kind]
    moving(cx, beat, t, t + d)
    return t + d


def text_in(cx, beat, sel, t, font="sans", style=None, chars=10):
    """Headline entrance by face: sans rises letter by letter (or stamps), the italic serif accent rises letter by
    letter with a small lean, mono labels track in."""
    if style in ("slam", "stamp"):
        end = enter(cx, beat, sel, t, "stamp", **{"from": 1.9, "blur": 22, "dur": 0.24})
        squash(cx, beat, sel, end, k=0.9)
        return end
    if style == "pop":
        return enter(cx, beat, sel, t, "pop", **{"from": 0.6})
    if font == "mono":
        return enter(cx, beat, sel, t, "trackIn", **{"from": 1.5, "blur": 8, "dur": 0.3})
    st = 0.034 if font == "serif" else 0.026
    st = min(st, 0.42 / max(1, chars))          # a long line still lands inside ~0.85 s
    return enter(cx, beat, sel, t, "letters", **{"stagger": round(st, 4), "rot": 8 if font == "serif" else 3,
                                                 "blur": 10, "dur": 0.42})


def land(cx, beat, sel, t, kind="rise"):
    """Graphic (non-text) entrances. rise: blur + scale + lift. pop: overshoot. slam: stamp + squash. slide: smear in.
    cut: a fast blur settle (the element arrives with its beat). sheet: a paper sheet flies in, tilted, and lands."""
    if kind == "sheet":
        return fly(cx, beat, sel, t, {"y": 420, "rotation": 7, "scale": 0.86, "blur": 16}, dur=0.55, ease="land")
    if kind == "pop":
        return enter(cx, beat, sel, t, "pop", **{"from": 0.55})
    if kind == "slam":
        end = enter(cx, beat, sel, t, "stamp", **{"from": 1.8, "blur": 20, "dur": 0.24})
        squash(cx, beat, sel, end, k=0.9)
        return end
    if kind == "slide":
        return enter(cx, beat, sel, t, "smear", **{"x": -150, "blur": 22, "dur": 0.18})
    if kind == "drop":
        return enter(cx, beat, sel, t, "drop", **{"y": -460, "rot": -8})
    if kind == "cut":
        return enter(cx, beat, sel, t, "blurIn", **{"y": 30, "scale": 0.95, "blur": 10, "dur": 0.32})
    return enter(cx, beat, sel, t, "blurIn", **{"y": 54, "scale": 0.92, "blur": 14, "dur": 0.42})


def fly(cx, beat, sel, t, frm, dur=0.5, ease="land"):
    """A custom fromTo entrance: frm {y, x, rotation, scale, blur} -> rest."""
    if not live(cx, beat, t):
        return t
    hide(cx, sel)
    t = preroll(beat, t)
    f = {"autoAlpha": 0, "x": frm.get("x", 0), "y": frm.get("y", 0), "rotation": frm.get("rotation", 0),
         "scale": frm.get("scale", 1), "filter": f"blur({frm.get('blur', 0)}px)"}
    to = {"autoAlpha": 1, "x": 0, "y": 0, "rotation": 0, "scale": 1, "filter": "blur(0px)", "duration": dur,
          "ease": E[ease], "immediateRender": False}
    cx.tw.append(f"tl.fromTo({_js(sel)},{_js(f)},{_js(to)},RRM.q({t:.4f}));")
    moving(cx, beat, t, t + dur)
    return t + dur


def draw(cx, beat, sel, t, dur=0.5):
    """A stroke (path with pathLength=1, dasharray 1, dashoffset 1 in the markup) draws on."""
    if not live(cx, beat, t):
        cx.init.append(f"gsap.set({_js(sel)},{{strokeDashoffset:0}});")
        return t
    t = preroll(beat, t)
    cx.tw.append(f"tl.fromTo({_js(sel)},{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:{dur:.3f},"
                 f"ease:{_js(E['draw'])},immediateRender:false}},RRM.q({t:.4f}));")
    moving(cx, beat, t, t + dur)
    return t + dur


def grow_x(cx, beat, sel, t, dur=0.45, origin="0% 50%", to=1.0):
    """A bar or rule grows from one side (scaleX 0 -> to)."""
    if not live(cx, beat, t):
        cx.init.append(f"gsap.set({_js(sel)},{{scaleX:{to},transformOrigin:{_js(origin)}}});")
        return t
    cx.init.append(f"gsap.set({_js(sel)},{{scaleX:0,transformOrigin:{_js(origin)}}});")
    cx.tw.append(f"tl.to({_js(sel)},{{scaleX:{to},duration:{dur:.3f},ease:{_js(E['glide'])}}},RRM.q({t:.4f}));")
    moving(cx, beat, t, t + dur)
    return t + dur


def squash(cx, beat, sel, t, k=0.86):
    """Impact squash + elastic settle right after a stamp lands (weight)."""
    if not live(cx, beat, t):
        return
    cx.tw.append(f"RRM.squash(tl,document.querySelector({_js(sel)}),{t:.4f},{{k:{k},origin:'50% 70%'}});")
    moving(cx, beat, t, t + 0.4)


def bob(cx, beat, sel, t0, t1, amp=7, period=1.3, phase=0.0):
    """Idle float after landing (secondary motion): explicit sine half-cycles, no repeat, seek-safe."""
    t, k = t0 + phase, 0
    while t + period / 2 < t1:
        y = -amp if k % 2 == 0 else amp * 0.4
        cx.tw.append(f"tl.to({_js(sel)},{{y:{y},duration:{period / 2:.3f},ease:{_js(E['drift'])}}},RRM.q({t:.4f}));")
        t += period / 2
        k += 1


def roll(cx, beat, col_sel, t, steps, step_h, dur=0.62):
    """Odometer: the digit column rolls up `steps` rows and lands (counter tick)."""
    if not live(cx, beat, t):
        cx.init.append(f"gsap.set({_js(col_sel)},{{y:{-steps * step_h}}});")
        return t
    cx.tw.append(f"tl.fromTo({_js(col_sel)},{{y:0,filter:'blur(6px)'}},{{y:{-steps * step_h},filter:'blur(0px)',"
                 f"duration:{dur:.3f},ease:{_js(E['snap'])},immediateRender:false}},RRM.q({t:.4f}));")
    moving(cx, beat, t, t + dur)
    return t + dur


def sweep(cx, beat, sel, t0, t1, every=1.15, dur=0.7):
    """A light band sweeps across a box again and again (a result loading): secondary motion while the beat holds."""
    t = t0
    while t + dur < t1 - 0.05:
        cx.tw.append(f"tl.fromTo({_js(sel)},{{xPercent:-120}},{{xPercent:220,duration:{dur:.3f},ease:{_js(E['camera'])},"
                     f"immediateRender:false}},RRM.q({t:.4f}));")
        moving(cx, beat, t, t + dur)
        t += every


def jitter(cx, beat, sel, t0, t1, base, amp=1.6, step=0.2, seed=5, arc=None):
    """A live reading: the needle hunts around its value (seeded, smooth). arc: a value-arc path (pathLength 1) that
    follows the needle (rotation -90..90 maps to dashoffset 1..0)."""
    t, i = t0, 0
    while t + step < t1:
        v = base + amp * math.sin(i * 1.9 + seed) * (0.6 + 0.4 * math.sin(i * 0.7 + seed * 2))
        cx.tw.append(f"tl.to({_js(sel)},{{rotation:{v:.2f},duration:{step:.3f},ease:{_js(E['drift'])}}},RRM.q({t:.4f}));")
        if arc:
            cx.tw.append(f"tl.to({_js(arc)},{{strokeDashoffset:{1 - (v + 90) / 180:.4f},duration:{step:.3f},"
                         f"ease:{_js(E['drift'])}}},RRM.q({t:.4f}));")
        t += step
        i += 1
    if t0 < t1:
        moving(cx, beat, t0, t1)


def kicker_rule(cx, beat, uid, t, t1, label_w, y=14, w=900, live_draw=True):
    """Magazine kicker rule: two hairlines drawing OUT from the label to the margins, a dot at each end.
    -> html (absolute, in the insert's own coordinates; top at y)."""
    x0, x1 = 540 - w / 2, 540 + w / 2
    g = label_w / 2 + 30
    d = (f'<path d="M{540 - g:.0f},{y} L{x0:.0f},{y}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>'
         f'<path d="M{540 + g:.0f},{y} L{x1:.0f},{y}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>')
    dots = f'<circle cx="{x0:.0f}" cy="{y}" r="6"/><circle cx="{x1:.0f}" cy="{y}" r="6"/>'
    if live_draw:
        draw(cx, beat, f"#{uid} path", t, 0.55)
        enter(cx, beat, f"#{uid} g", t + 0.5, "pop", **{"from": 0.2, "dur": 0.3})
    else:
        cx.init.append(f"gsap.set('#{uid} path',{{strokeDashoffset:0}});")
    return (f'<svg class="krule" id="{uid}" viewBox="{x0 - 8:.0f} 0 {w + 16:.0f} {y * 2}" '
            f'style="left:{x0 - 8:.0f}px;width:{w + 16:.0f}px;height:{y * 2}px" '
            f'data-box="card" data-t0="{max(t, beat["t0"]):.3f}" data-t1="{t1:.3f}">{d}<g>{dots}</g></svg>')


def label_w(text, px=28, spacing=0.24):
    return len(text) * px * (0.6 + spacing)


# ----------------------------------------------------------------------------------------------- stage rig
def _ein(p):        # expo.out
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def _cam(p):        # power2.inOut
    return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2


def _in3(p):        # power3.in
    return p ** 3


def _noise(seed, t, freqs=(0.19, 0.33, 0.57)):
    return sum(math.sin(2 * math.pi * f * t + seed * (k + 1) * 1.7) for k, f in enumerate(freqs)) / len(freqs)


def _area_cy(cx, layout):
    if layout == "card":
        return (220 + cx.card["top"] - cx.card.get("caption_band", 128)) / 2
    if layout == "stage":
        return (220 + cx.stage_bottom) / 2
    return 520


def _beat_cam(cx, b, i, nxt_whip, prev_whip, cfg):
    f0, f1 = int(round(b["t0"] * FPS)), int(round(b["t1"] * FPS))
    n = max(1, f1 - f0)
    dur = n / FPS
    cy = _area_cy(cx, b["layout"])
    push = min(cfg["push"], 0.011 * dur)
    steps = []
    acc = 0.0
    for (t, y, k) in sorted(cx.__dict__.get("_me_focus", {}).get(b["id"], [])):
        if t < b["t0"] + 0.15 or t > b["t1"] - 0.3:
            continue
        ds = min(cfg["step"] * k, cfg["cap"] - push - acc)
        if ds <= 0.002:
            break
        acc += ds
        dy = 0.0 if y is None else max(-28.0, min(28.0, (cy - y) * 0.16))
        steps.append((int(round(t * FPS)), ds, dy))
    rows, prev = [], None
    for f in range(f0, f1):
        tt = (f - f0) / FPS
        s = 1 + push * (f - f0) / n
        x = 6.0 * cfg["drift"] * _noise(i + 1, f / FPS)
        y = 4.5 * cfg["drift"] * _noise(i + 7, f / FPS, (0.13, 0.29, 0.47))
        r = 0.18 * cfg["drift"] * _noise(i + 3, f / FPS, (0.11, 0.23))
        blur = 0.0
        for (sf, ds, dy) in steps:
            if f >= sf:
                p = _cam(min(1.0, (f - sf) / 14))
                s += ds * p
                y += dy * p
        if prev_whip:                       # graphic changed inside the shot: the new one whips in from the right
            p = min(1.0, tt / (7 / FPS))
            if p < 1:
                e = 1 - _ein(p)
                x += 250 * e
                blur = max(blur, 18 * e)
        elif tt < 12 / FPS:                 # on a cut: settle (graphics-only beats carry the frame alone: harder)
            p = _ein(tt / (12 / FPS))
            k = 1.6 if b["layout"] == "stage" else 1.0
            s += cfg["settle"] * k * (1 - p)
            y += 26 * k * (1 - p)
        if nxt_whip and f >= f1 - 4:        # and the outgoing one whips out to the left
            p = (f - (f1 - 4) + 1) / 4
            x -= 250 * _in3(p)
            blur = max(blur, 18 * p)
        row = [f, round(s, 4), round(x, 1), round(y, 1), round(r, 3), round(blur, 1)]
        if prev is None or row[1:] != prev[1:]:
            rows.append(row)
        prev = row
    return rows, cy


def _cuts(cx):
    return {round(s["t0"], 2) for s in getattr(cx, "segs", [])}


def stage(cx, beats, placement, segs=None, mcfg=None):
    """Stage rig + card depth. Called by split/compose.py (style hook) after the beats render, before the motion plan."""
    if mcfg is None or mcfg.get("level") == "simple":
        return
    lvl = mcfg.get("level", "polished")
    cfg = {"polished": {"push": 0.045, "step": 0.022, "cap": 0.08, "settle": 0.05, "whip": True, "card_rise": 300, "float": 10.0, "drift": 1.0},
           "showreel": {"push": 0.06, "step": 0.03, "cap": 0.1, "settle": 0.07, "whip": True, "card_rise": 360, "float": 12.0, "drift": 1.3}}[lvl]
    cuts = _cuts(cx)
    shown = [b for b in beats if b.get("items")]
    swaps = set()
    for a, b in zip(shown, shown[1:]):
        if abs(a["t1"] - b["t0"]) < 1e-3 and round(b["t0"], 2) not in cuts and b["layout"] == a["layout"] \
                and b["layout"] in ("card", "stage") and cfg["whip"]:
            swaps.add(b["id"])
    stage_y = {}
    for i, b in enumerate(shown):
        nxt = shown[i + 1] if i + 1 < len(shown) else None
        rows, cy = _beat_cam(cx, b, i, bool(nxt and nxt["id"] in swaps), b["id"] in swaps, cfg)
        if not rows:
            continue
        cx.init.append(f"gsap.set('#{b['id']}',{{transformOrigin:'540px {cy:.0f}px'}});")
        cx.tw.append(f"RRM.keys(tl,'#{b['id']}',['scale','x','y','rotation','blur'],{_js(rows)});")
        for r in rows:
            stage_y[r[0]] = r[3]
        if b["id"] in swaps:
            cx.event(b["t0"], "whoosh", f"stage whip {b['id']}")
    _card_rig(cx, placement, stage_y, cfg)


def _card_rig(cx, placement, stage_y, cfg):
    """The speaker card as a depth layer: rise in, sink out before a graphics-only beat, parallax against the stage."""
    spans = []
    for p in placement:
        if p["layout"] == "card" and spans and abs(spans[-1]["t1"] - p["t0"]) < 1e-3 and spans[-1]["layout"] == "card":
            spans[-1]["t1"] = p["t1"]
            continue
        spans.append({"t0": p["t0"], "t1": p["t1"], "layout": p["layout"]})
    rows, last = [], None
    for i, s in enumerate(spans):
        if s["layout"] != "card":
            continue
        prev = spans[i - 1]["layout"] if i else None
        nxt = spans[i + 1]["layout"] if i + 1 < len(spans) else None
        f0, f1 = int(round(s["t0"] * FPS)), int(round(s["t1"] * FPS))
        y_hist = 0.0
        for f in range(f0, f1):
            tt = (f - f0) / FPS
            sy = stage_y.get(f, y_hist)
            y_hist = sy
            # parallax against the stage camera + the card's own slow float (a physical card, never locked off)
            y = -0.45 * sy + cfg["float"] * math.sin(2 * math.pi * (f - f0) / FPS / 3.2) + 2.0 * _noise(f0 % 97 + 11, f / FPS, (0.12, 0.27))
            if prev is not None and prev != "card" and f0 > 0 and tt < 14 / FPS:
                y += cfg["card_rise"] * (1 - _ein(tt / (14 / FPS)))
            if nxt in ("stage", "media") and f >= f1 - 5:
                y += 360 * _in3((f - (f1 - 5) + 1) / 5)
            x = 0.6 * cfg["float"] * math.sin(2 * math.pi * (f - f0) / FPS / 4.6 + 1.1)
            row = [f, round(x, 1), round(y, 1)]
            if last is None or row[1:] != last[1:]:
                rows.append(row)
            last = row
        if last is not None and last[2] != 0:
            rows.append([f1, 0, 0])
            last = [f1, 0, 0]
    if rows:
        cx.tw.append(f"RRM.keys(tl,'#sp,#cardsh',['x','y'],{_js(rows)});")


def caption_roll(cx, caps, mcfg):
    """One-word captions swap on a snap: when the next word follows straight on, the current word rolls up and out
    (3 frames, blur) while the engine rolls the next one in. Captions sit outside the camera; this is their only exit."""
    if not mcfg or mcfg.get("level") == "simple" or mcfg.get("captions") == "plain":
        return
    for i, c in enumerate(caps):            # the word box itself rides up into place under the engine's rise
        if c.get("layout") in ("card", "stage") and c["t0"] >= 1.0 / FPS:
            cx.tw.append(f"tl.fromTo('#c{i}',{{y:40}},{{y:0,duration:0.16,ease:{_js(E['snap'])},immediateRender:false}},"
                         f"RRM.q({c['t0']:.4f}));")
    for i, (c, n) in enumerate(zip(caps, caps[1:])):
        if abs(n["t0"] - c["t1"]) > 0.02 or c["t1"] - c["t0"] < 0.2:
            continue
        t = c["t1"] - 0.1
        cx.tw.append(f"tl.to('#c{i} .pill',{{y:-44,scale:0.92,filter:'blur(8px)',autoAlpha:0,duration:0.1,"
                     f"ease:{_js(E['exit'])}}},RRM.q({t:.4f}));")


CSS = """
.krule{position:absolute;top:0;overflow:visible;pointer-events:none}
.krule path{fill:none;stroke:color-mix(in srgb,var(--ink) 55%,transparent);stroke-width:2.5;stroke-linecap:round}
.krule circle{fill:var(--accent)}
.krule g{transform-box:fill-box;transform-origin:50% 50%}
.mark{position:absolute;left:-.06em;right:-.06em;top:52%;height:40%;border-radius:10px;background:color-mix(in srgb,var(--hl) 62%,transparent);
  transform:skewX(-8deg);z-index:-1}
.odo{display:inline-block;overflow:hidden;vertical-align:bottom}
.odo .col{display:block}
.odo .col span{display:block;text-align:center}
.sweep{position:absolute;top:0;bottom:0;left:0;width:45%;
  background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--accent) 38%,transparent),transparent)}
"""
