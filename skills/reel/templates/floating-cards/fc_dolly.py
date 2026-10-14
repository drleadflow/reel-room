"""Floating Cards: the parallax slider dolly on the speaker plate.

A slow lateral camera slide (with a slight rise and a breathing push) that changes direction on phrase starts and
cuts. The plate moves, the cards do not: they read as floating in FRONT of him at a different depth, which is the
style's whole idea. It also keeps a calm talking head from ever sitting dead still (QA dead_frames / motion_density).

The plate video sits alone in its own wrapper (#fcDolly, inside the engine camera); the live behind-head layer gets
an identical inner wrapper (#fcDollyB) so the word and the cut-out stay locked to the head. Overscan: the plate is
scaled about the frame centre so a slide of `amp` px never shows an edge.

project.json style_cfg "dolly": {"amp": 36, "rise": 8, "push": 0.016, "leg": [1.6, 3.2]}  or  false.
"""
FPS = 30
W, H = 1080, 1920


def legs(words, segments, frames, lo=1.6, hi=3.2, gap=0.22):
    """Turn points (seconds): cuts and phrase starts, at least `lo` s apart; long legs split at `hi`."""
    cuts = [s["frame"] / FPS for s in segments[1:]]
    starts = [float(w["start"]) for a, w in zip(words, words[1:]) if float(w["start"]) - float(a["end"]) >= gap]
    cand = sorted(set([round(t, 3) for t in cuts + starts]))
    out, last = [0.0], 0.0
    end = frames / FPS
    for t in cand:
        while t - last > hi:
            last += hi * 0.75
            out.append(round(last, 3))
        if t - last >= lo and end - t >= lo * 0.6:
            out.append(t)
            last = t
    while end - last > hi:
        last += hi * 0.75
        out.append(round(last, 3))
    out.append(round(end, 3))
    return out


def plan(proj, cfg):
    if cfg is False or cfg is None:
        return None
    amp, rise, push = float(cfg.get("amp", 36)), float(cfg.get("rise", 8)), float(cfg.get("push", 0.016))
    lo, hi = cfg.get("leg", [1.6, 3.2])
    base = 1.0 + (amp + 6) / (W / 2)                # overscan: the slide never shows an edge
    pts = legs(proj.words_raw, proj.segments, proj.frames, lo, hi)
    keys = []
    for i, t in enumerate(pts):
        s = 1 if i % 2 == 0 else -1
        keys.append({"t": t, "x": round(-amp * s, 1), "y": round(-rise * s, 1),
                     "scale": round(base + (push if i % 4 in (1, 2) else 0.0), 4)})
    return {"base": round(base, 4), "keys": keys}


def js(p, sel="#fcDolly,#fcDollyB"):
    if not p:
        return []
    k0 = p["keys"][0]
    out = [f"tl.set('{sel}',{{x:{k0['x']},y:{k0['y']},scale:{k0['scale']},transformOrigin:'540px 960px'}},0);"]
    for a, b in zip(p["keys"], p["keys"][1:]):
        out.append(f"tl.to('{sel}',{{x:{b['x']},y:{b['y']},scale:{b['scale']},duration:{b['t'] - a['t']:.4f},"
                   f"ease:'sine.inOut'}},{a['t']:.4f});")
    return out


def css():
    return ".fc-dolly{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 960px}\n"


def wrap_plate(html):
    """<video id="aroll" ...></video> -> <div id="fcDolly" class="fc-dolly"><video ...></video></div>"""
    i = html.find('<video id="aroll"')
    if i < 0:
        return html
    j = html.find("</video>", i) + len("</video>")
    return html[:i] + '<div id="fcDolly" class="fc-dolly">' + html[i:j] + "</div>" + html[j:]


def at_frame(p, f):
    """(x, y, scale) of the dolly on frame f (QA and planning helpers)."""
    import math
    if not p:
        return 0.0, 0.0, 1.0
    t = f / FPS
    ks = p["keys"]
    for a, b in zip(ks, ks[1:]):
        if a["t"] <= t <= b["t"]:
            u = (t - a["t"]) / max(1e-6, b["t"] - a["t"])
            e = -(math.cos(math.pi * u) - 1) / 2
            return tuple(a[k] + (b[k] - a[k]) * e for k in ("x", "y", "scale"))
    k = ks[-1]
    return k["x"], k["y"], k["scale"]
