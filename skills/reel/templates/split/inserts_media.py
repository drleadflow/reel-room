"""Media top-panel inserts: still image (Ken Burns), before/after flip, video B-roll, 2x2 video collage.
Video uses the framework's media attributes (data-start / data-media-start / data-duration / data-track-index) and is
never nested inside another timed element."""
from ctx import esc, floor5, snap


def _video(cx, beat, src, x, y, w, h, media_start=0.0, autocrop=True):
    cx.check_asset(src)
    vid = cx.uid("vid")
    a0 = beat.get("anchor_t0", beat["t0"])
    start = max(beat["t0"], 0.0)
    ms = media_start + (start - a0)
    length = beat["t1"] - start
    total = cx.media_dur(src)
    if total is not None and ms + length > total + 0.03:
        cx.warn(f"video {src} is {total:.2f}s but beat {beat['id']} needs {ms + length:.2f}s; it will end early")
        length = max(total - ms, 0.1)
    elif total is None or ms + length + 3 / 30 <= total:
        length += 3 / 30   # coverage gate: the layer outlives its window by 3 frames (the beat hides it on time)
    dur = f'data-start="{floor5(start)}" data-media-start="{floor5(ms)}" data-duration="{floor5(length)}" data-track-index="{cx.next_track()}"'
    crop = cx.crop_of(src) if autocrop else None
    if crop:  # hide baked-in black bars: scale the video so the clean region covers the tile
        sw, sh, cxp, cyp, cw, ch = crop
        k = max(w / cw, h / ch)
        left, top = -(cxp * k) - (cw * k - w) / 2, -(cyp * k) - (ch * k - h) / 2
        vstyle = f"left:{left:.1f}px;top:{top:.1f}px;width:{sw * k:.1f}px;height:{sh * k:.1f}px"
    else:
        vstyle = "left:0;top:0;width:100%;height:100%"
    return (f'<div class="vwrap" data-layout-allow-overflow style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" {cx.box("video", start, beat["t1"])}>'
            f'<video id="{vid}" class="vid" src="{esc(src)}" muted playsinline {dur} style="{vstyle}"></video></div>')


def video(cx, beat, a):
    x, y, w, h = a.get("box", [0, 0, 1080, 960])
    return _video(cx, beat, a["src"], x, y, w, h, a.get("media_start", 0.0), a.get("autocrop", True))


def collage(cx, beat, a):
    srcs = a["srcs"]
    x0, y0, w, h = a.get("box", [0, 200, 1080, 760])
    gap = a.get("gap", 4)
    tw, th = (w - gap) // 2, (h - gap) // 2
    starts = a.get("media_start", [0.0] * 4)
    out = []
    for i, s in enumerate(srcs[:4]):
        r, c = divmod(i, 2)
        out.append(_video(cx, beat, s, x0 + c * (tw + gap), y0 + r * (th + gap), tw, th,
                          starts[i] if i < len(starts) else 0.0, a.get("autocrop", True)))
    return "".join(out)


def image(cx, beat, a):
    cx.check_asset(a["src"])
    iid, t0, t1 = cx.uid("img"), beat["t0"], beat["t1"]
    x, y, w, h = a.get("box", [0, 220, 1080, 720])
    contain = a.get("fit") == "contain"
    css = "background-repeat:no-repeat;"
    if contain:
        iw, ih = cx.img_size(a["src"])
        s = min(w / iw, h / ih)
        bw, bh = round(iw * s), round(ih * s)
        x, y, w, h = x + (w - bw) // 2, y + (h - bh) // 2, bw, bh
        css += "border-radius:26px;"
    if a.get("kenburns", True):
        a0 = beat.get("anchor_t0", t0)
        full = (beat["t1"] - a0) if a0 == t0 else (beat["t1"] - t0)
        cx.tw.append(f'tl.fromTo("#{iid}i",{{scale:1}},{{scale:1.06,duration:{max(full, .1):.3f},ease:"none"}},{snap(t0)});')
    pill = ""
    p = a.get("pill")
    if p:
        pid = cx.uid("ip")
        pt = cx.when(p.get("at"), beat, 0.45)
        cx.enter(beat, f"#{pid}", pt, {"opacity": 0, "y": 22, "scale": 0.96}, {"opacity": 1, "y": 0, "scale": 1}, dur=0.3)
        b = f"<b>{esc(p['b'])}</b>" if p.get("b") else ""
        pill = (f'<div class="imgpill" style="top:{y + h - 100}px"><div class="in" id="{pid}" data-fit="980,30" '
                f'{cx.box("text", max(pt, t0), t1, True)}>{esc(p["a"])}{b}</div></div>')
    return (f'<div class="imgbox" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{"border-radius:26px;" if contain else ""}'
            f'box-shadow:{"0 20px 50px rgba(0,0,0,.18)" if contain else "none"}" {cx.box("image", t0, t1)}>'
            f'<div class="im" id="{iid}i" style="background-image:url(\'{esc(a["src"])}\');background-size:cover;{css}"></div></div>{pill}')


def flip(cx, beat, a):
    """Before/after cards: stacked, a quick 0.34 s Y-flip to the next one."""
    srcs = a["srcs"]
    t0, t1 = beat["t0"], beat["t1"]
    x, y, w, h = a.get("box", [0, 220, 1080, 720])
    iw, ih = cx.img_size(srcs[0])
    s = min(w / iw, h / ih)
    bw, bh = round(iw * s), round(ih * s)
    bx, by = x + (w - bw) // 2, y + (h - bh) // 2
    times = a.get("at") or [None] * len(srcs)
    out = []
    for i, src in enumerate(srcs):
        cx.check_asset(src)
        fid = cx.uid("fl")
        if i:
            t = cx.when(times[i] if i < len(times) and times[i] is not None else None, beat,
                        (t1 - t0) * i / len(srcs))
            cx.enter(beat, f"#{fid}", t, {"opacity": 0, "rotationY": -90, "transformPerspective": 1400},
                     {"opacity": 1, "rotationY": 0, "transformPerspective": 1400}, dur=0.34, ease="power2.out")
        out.append(f'<div class="abs" id="{fid}" style="left:{bx}px;top:{by}px;width:{bw}px;height:{bh}px;border-radius:26px;'
                   f'background:url(\'{esc(src)}\') center/cover no-repeat;box-shadow:0 20px 50px rgba(0,0,0,.2)" '
                   f'{cx.box("image", t0, t1)}></div>')
    return "".join(out)
