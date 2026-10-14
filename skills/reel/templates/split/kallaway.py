"""kallaway.py: the inserts the kallaway preset (presets.py) places, in our own look.

  topic_banner  overlay   a label-pill tag (3 to 5 words) readable on frame 1, holds about 2.5 s, lifts away
  proof_screen  split     a framed screen (screenshot or recording) in the top slot, a spotlight on the row, an
                          odometer on the key number, an annotation arrow on the spoken noun (all from the kit)
  head_bubble   overlay   kit head-bubble hosted on the split plate (plate transform, seam clip, face track, camera
                          follower), over a full-screen `behind` graphic (a diagram insert or a media path)
  diagram       (behind)  a hub and nodes that rise in on their words, laid out clear of the bubble and the captions
  comment_cta   overlay   kit comment-cta (comment the keyword, the DM lands; land it on a cut with "#seg")
"""
import kitbridge
from ctx import esc, snap

SPLIT_REGION = (0, 960, 1080, 1920)


def topic_banner(cx, b, a):
    """Label-pill topic tag, readable from frame 1 (no fade-in), a soft settle, then it lifts away."""
    text = str(a.get("text", "")).upper()
    n = len(text.split())
    if not 3 <= n <= 5:
        cx.warn(f"topic banner '{text}' has {n} words; the preset wants 3 to 5")
    bid = cx.uid("tb")
    t0, t1 = b["t0"], b["t0"] + float(a.get("dur", 2.5))
    cx.tw.append(f"tl.fromTo('#{bid}',{{scale:1.035}},{{scale:1,duration:0.6,ease:'power2.out',immediateRender:false}},{snap(t0)});")
    cx.tw.append(f"tl.to('#{bid}',{{y:-26,autoAlpha:0,filter:'blur(6px)',duration:0.2,ease:'power3.in'}},{snap(t1)});")
    return (f'<div class="tb-wrap"><div class="tb" id="{bid}"><i class="tb-dot"></i>'
            f'<span data-fit="880,30" {cx.box("text", t0, t1, True)}>{esc(text)}</span></div></div>')


def _row_box(a, x0, y0, k):
    r = a.get("row")
    return None if not r else (x0 + r[0] * k, y0 + r[1] * k, r[2] * k, r[3] * k)


def proof_screen(cx, beat, a):
    """A framed screen in the top slot; spotlight on `row`, odometer on `value`, arrow on the noun (`arrow`)."""
    import deck
    src = a["src"]
    cx.check_asset(src)
    iw, ih = a.get("img_size") or cx.img_size(src)
    x0, w = 60, 960
    k = w / iw
    bar = 58
    top = int(a.get("y", 250))
    h = round(ih * k)
    sid = cx.uid("ps")
    t0, t1 = beat["t0"], beat["t1"]
    cx.enter(beat, f"#{sid}", t0, {"y": 60, "scale": 0.94, "opacity": 0.55, "filter": "blur(10px)"},   # visible on the cut
             {"y": 0, "scale": 1, "opacity": 1, "filter": "blur(0px)"}, dur=0.42, ease="expo.out")
    cx.event(t0, "whoosh", "proof screen")
    title = esc(a.get("title", "Results"))
    html = (f'<div class="ps" id="{sid}" style="left:{x0}px;top:{top}px;width:{w}px;height:{h + bar}px" '
            f'{cx.box("card", t0, t1)}><div class="ps-bar"><i></i><i></i><i></i><b {cx.box("text", t0, t1, True)}>{title}</b>'
            + (f'<em {cx.box("text", t0, t1, True)}>{esc(a["tag"])}</em>' if a.get("tag") else "")
            + f'</div><div class="ps-img" style="height:{h}px;background-image:url(\'{esc(src)}\')"></div></div>')
    kt = kitbridge.kit(cx, beat)
    row = _row_box(a, x0, top + bar, k)
    parts = [html]
    if row:
        sp = kt.spotlight(row, at=a.get("spot_at", 0.5), shape="box", dim=0.5, feather=10, pad=12, label=a.get("spot_label"))
        parts.append(kitbridge.mount(cx, sp))
        deck.focus(cx, beat, sp.t0 + 0.1, row[0] + row[2] / 2, row[1] + row[3] / 2, 1.05, "proof row")
    if a.get("value"):
        v = a["value"]
        od = kt.odometer(float(v["value"]), at=v.get("in", 0.3), land=v.get("at"), decimals=v.get("decimals", 0),
                         prefix=v.get("prefix", ""), suffix=v.get("suffix", ""), label=v.get("label"), size=v.get("size", 110),
                         card=True, x=v.get("x", 640), y=v.get("y", 640), w=v.get("w", 360))
        parts.append(kitbridge.mount(cx, od))
    if a.get("arrow"):
        ar = a["arrow"]
        an = kt.annotate(tuple(ar["to"]), kind=ar.get("kind", "arrow"), at=ar.get("at", 1.2), label=ar.get("label"),
                         frm=tuple(ar["from"]) if ar.get("from") else None, size=ar.get("size", 60), seed=ar.get("seed", 5),
                         bend=ar.get("bend", 0.22))
        parts.append(kitbridge.mount(cx, an))
    return "".join(parts)


def diagram(cx, b, a):
    """Full-frame hub-and-nodes diagram (the graphic behind a head bubble). Title right of the bubble, hub above the
    caption band, nodes in a 2 x 2 grid under it; each node rises in on its word, the hub pulses on `pulse`."""
    did = cx.uid("dg")
    t_end = b["t1"]
    after = b["t0"]
    out = [f'<div class="dg" id="{did}">']
    if a.get("title"):
        out.append(f'<div class="dg-title" {cx.box("text", b["t0"], t_end, True)}>{esc(a["title"])}</div>')
    out.append(f'<div class="dg-hub" id="{did}h" {cx.box("text", b["t0"], t_end, True)}>{esc(a.get("hub", ""))}</div>')
    nodes = a.get("nodes", [])[:4]
    paths, stops = [], []
    for i, nd in enumerate(nodes):
        r, c = divmod(i, 2)
        x, y = 110 + c * 450, 1150 + r * 160
        paths.append(f'<path d="M540 800 C540 980 {x + 190} 980 {x + 190} {y}"/>')
        t = cx.cue(nd["at"], b, after=after, fallback=0.8) if nd.get("at") is not None else after + 0.8
        stops.append((t, x + 190, y + 62))
        after = t + 0.05
        nid = f"{did}n{i}"
        cx.enter(b, f"#{nid}", t, {"opacity": 0, "y": 44, "scale": 0.9, "filter": "blur(8px)"},
                 {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, dur=0.42, ease="expo.out")
        cx.event(t, "pop" if i == 0 else "cut", f"diagram node {nd.get('text')}")
        out.append(f'<div class="dg-node" id="{nid}" style="left:{x}px;top:{y}px" {cx.box("text", t, t_end, True)}>'
                   f'{esc(nd.get("text", ""))}</div>')
    out.insert(1, f'<svg class="dg-lines" viewBox="0 0 1080 1920" width="1080" height="1920">{"".join(paths)}</svg>')
    _glide(cx, f"#{did}", b, stops)
    if a.get("pulse"):
        tp = cx.cue(a["pulse"], b, after=after, fallback=0.4)
        cx.tw.append(f"tl.fromTo('#{did}h',{{scale:1.08}},{{scale:1,duration:0.4,ease:'back.out(2.2)',immediateRender:false}},{snap(tp)});")
        cx.event(tp, "cut", "diagram hub pulse")
    return "".join(out) + "</div>"


def _ease_io(p):
    p = min(1.0, max(0.0, p))
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def _glide(cx, sel, b, stops, k=0.1, dur=0.6):
    """The diagram's own camera: it glides toward each node as it lands (a little closer each time, a 10 % pull toward
    the node),
    one tl.set per frame (seek-safe, never two tweens on the same property)."""
    f0, f1 = int(round(b["t0"] * 30)), int(round(b["t1"] * 30))
    cur, rows, prev = (1.0, 0.0, 0.0), [], None
    targets = [(t, (1.03 + 0.015 * i, (540 - x) * k, (900 - y) * k)) for i, (t, x, y) in enumerate(stops)]
    for f in range(f0, f1):
        t = f / 30
        state = (1.0, 0.0, 0.0)
        for ts, tg in targets:
            if t < ts:
                break
            p = _ease_io((t - ts) / dur)
            state = tuple(a + (c - a) * p for a, c in zip(state, tg))
        row = (round(state[0], 4), round(state[1], 1), round(state[2], 1))
        if row != prev:
            rows.append(f"tl.set('{sel}',{{scale:{row[0]},x:{row[1]},y:{row[2]}}},{snap(t)});")
        prev = row
        cur = state
    cx.tw.extend(rows)
    return cur


def _face_rows(cx, t0, t1):
    rows = [(r[0], r[3]["x"] + r[3]["w"] / 2, r[3]["y"] + r[3]["h"] / 2, r[3]["w"]) for r in cx._heads
            if t0 - 0.25 <= r[0] <= t1 + 0.25]
    return rows or [(t0, 540, 1310, 190)]


def _plate_at(cx, t):
    p = next((p for p in cx._slices if p["t0"] - 1e-4 <= t < p["t1"] and p.get("visible", True)), None)
    if p is None:
        raise SystemExit(f"head bubble at {t:.2f}s: no visible speaker plate there")
    region = SPLIT_REGION if p["layout"] == "split" else None
    if p["layout"] == "card":
        c = cx.card
        region = (c["inset"], c["top"], 1080 - c["inset"], 1920)
    return {"x": p.get("dx", 0), "y": p["dy"], "scale": p["scale"], "ox": p["ox"], "oy": p["oy"]}, region


def head_bubble(cx, b, a):
    """Kit head-bubble on the split plate. Overlay beat b = the window; `behind` = {"insert": "diagram", ...} or a path."""
    beh = a.get("behind")
    behind_html = diagram(cx, b, beh.get("args", {})) if isinstance(beh, dict) else beh
    kt = kitbridge.kit(cx, b)
    t_probe = b["t0"] + 1e-3
    plate, region = _plate_at(cx, t_probe)
    vig = float((getattr(cx, "motion_cfg", None) or {}).get("vignette") or 0.0)
    p = kt.head_bubble(at=a.get("at", 0.0), back=a.get("back"), corner=a.get("corner", "tl"), size=a.get("size", 300),
                       ring=a.get("ring", True), label=a.get("label"), face=_face_rows(cx, b["t0"], b["t1"]),
                       fit=a.get("fit", 1.18), plate=plate, clip=region, behind=behind_html, vignette=vig)
    t_in, t_end = p.meta["times"]["t_in"], p.meta["times"]["end"]
    for s in getattr(cx, "segs", []):
        if t_in + 0.02 < s["t0"] < t_end - 0.02:
            cx.warn(f"head bubble {t_in:.2f}-{t_end:.2f}s crosses the cut at {s['t0']:.2f}s; keep it inside one shot")
    seg = next((s for s in getattr(cx, "segs", []) if s["t0"] - 1e-4 <= t_in < s["t1"]), None)
    if seg and t_in - seg["t0"] < 0.5:     # no whole-frame transition on the cut the bubble starts from
        cm = dict(getattr(cx, "cut_motion", None) or {})
        cm[seg["id"]] = {**cm.get(seg["id"], {}), "transition": "none"}
        cx.cut_motion = cm
    cx.cam_followers = (getattr(cx, "cam_followers", None) or []) + [p.meta["cam_sel"]]
    cx.pip_windows = (getattr(cx, "pip_windows", None) or []) + [(round(t_in, 3), round(t_end, 3))]
    return kitbridge.mount(cx, p)


def cta(cx, b, a):
    """Keyword comment CTA (kit comment-cta) in the top slot. dm_at may be '#seg' (the DM lands on that cut)."""
    kt = kitbridge.kit(cx, b)

    def rel(spec):
        if isinstance(spec, str) and spec.startswith("#"):
            t = cx.when(spec, b)
            cx.cut_change(t)
            return round(t - b["t0"], 3)
        return spec
    p = kt.comment_dm(a["keyword"], at=a.get("at", 0.0), type_at=rel(a.get("type_at")), post=rel(a.get("post")),
                      dm_at=rel(a.get("dm_at")), dm_text=a.get("dm_text"), link_text=a.get("link_text"),
                      link_sub=a.get("link_sub"), y=a.get("y", 236), w=a.get("w", 900))
    return kitbridge.mount(cx, p)


def css(brand):
    c, f = brand["colors"], brand["fonts"]
    return f"""
.tb-wrap{{position:absolute;left:0;top:252px;width:1080px;display:flex;justify-content:center}}
.tb{{display:flex;align-items:center;gap:18px;height:84px;padding:0 36px 0 28px;border-radius:42px;background:{c['bg']};
  color:{c['ink']};font:800 38px/84px '{f['display']}',sans-serif;letter-spacing:.06em;white-space:nowrap;
  box-shadow:0 18px 36px rgba(20,10,12,.22),0 4px 10px rgba(20,10,12,.14),inset 0 0 0 1.5px rgba(255,255,255,.6)}}
.tb-dot{{width:18px;height:18px;border-radius:9px;background:{c['accent']};box-shadow:0 0 0 6px rgba(122,30,46,.16)}}
.ps{{position:absolute;border-radius:28px;overflow:hidden;background:#fff;
  box-shadow:0 34px 64px rgba(20,10,12,.24),0 10px 22px rgba(20,10,12,.14),inset 0 0 0 1.5px rgba(20,10,12,.08)}}
.ps-bar{{height:58px;display:flex;align-items:center;gap:10px;padding:0 22px;background:{c['bg']};border-bottom:1.5px solid rgba(20,10,12,.08)}}
.ps-bar i{{width:14px;height:14px;border-radius:7px;background:rgba(20,10,12,.18)}}
.ps-bar b{{margin-left:12px;font:700 24px/1 '{f['body']}',sans-serif;color:{c['ink']}}}
.ps-bar em{{margin-left:auto;font:800 18px/1 '{f['body']}',sans-serif;letter-spacing:.12em;color:{c['accent']};font-style:normal;
  padding:8px 12px;border-radius:10px;background:rgba(122,30,46,.10)}}
.ps-img{{width:100%;background-size:100% 100%;background-repeat:no-repeat}}
.cap .pill .cap-acc{{color:{c.get('highlight', c['accent'])}}}
.dg{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 900px}}
.dg-lines{{position:absolute;left:0;top:0}}.dg-lines path{{fill:none;stroke:{c['ink']};stroke-width:5;opacity:.16}}
.dg-title{{position:absolute;left:410px;top:290px;width:610px;font:900 62px/1.02 '{f['display']}',sans-serif;letter-spacing:-.035em;color:{c['ink']}}}
.dg-hub{{position:absolute;left:300px;top:610px;width:480px;height:190px;border-radius:46px;background:{c['accent']};color:{c['bg']};
  display:flex;align-items:center;justify-content:center;text-align:center;font:850 60px/1.02 '{f['display']}',sans-serif;
  letter-spacing:-.03em;box-shadow:0 30px 60px rgba(20,10,12,.24)}}
.dg-node{{position:absolute;width:380px;height:124px;border-radius:34px;background:#fff;color:{c['ink']};text-align:center;
  font:800 44px/124px '{f['display']}',sans-serif;letter-spacing:-.02em;box-shadow:0 22px 44px rgba(20,10,12,.16),0 4px 10px rgba(20,10,12,.10)}}
"""


INSERTS = {"topic_banner": topic_banner, "proof_screen": proof_screen, "head_bubble": head_bubble, "diagram": diagram,
           "comment_cta": cta}
