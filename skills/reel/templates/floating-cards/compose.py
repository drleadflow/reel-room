#!/usr/bin/env python3
"""Floating Cards template: bright full-frame talking head, frosted UI cards that fly in around the head in real 3D
on their words, land with an overshoot and a contact shadow, float while they hold, stack / fan / dock as the topic
moves and tumble away when struck out; single-word glow captions at chest height; one big word BEHIND the head
(live cut-out, letters rise one by one); a step HUD that docks at the top. Motion v2 camera and transitions on top.

  compose.py <project>            prepare (grade bake, cached) then write index.html + work/meta.json
  (normally run through stylekit/build.py, which also lints, renders, mixes SFX, masters, cuts loop/poster and QAs)

Everything content-specific lives in project.json "style_cfg" (see README.md); colours/fonts come from brand.json.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
sys.path.insert(0, HERE)
import kit  # noqa: E402
from kit import FPS, esc, frame_of  # noqa: E402
import fc_behind  # noqa: E402
import fc_cards as fc  # noqa: E402
import fc_dolly  # noqa: E402
import fc_style  # noqa: E402


# ---------------------------------------------------------------- timing helpers
def seg_frame(proj, sid):
    for s in proj.segments:
        if s["id"] == sid:
            return s["frame"]
    raise SystemExit(f"unknown segment '{sid}'")


def resolve(proj, spec, lo=0.0):
    """'seg:<id>' -> that cut's first frame (hard switch); '@word' -> word start; number -> seconds. Returns (frame, hard)."""
    if isinstance(spec, str) and spec.startswith("seg:"):
        return seg_frame(proj, spec[4:]), True
    if spec == "end":
        return proj.frames, True
    return frame_of(proj.at(spec, lo)), False


def at_t(proj, spec, lo=0.0):
    return resolve(proj, spec, lo)[0] / FPS


# ---------------------------------------------------------------- cards
def place_cards(proj, tl, cards):
    wins = []
    for c in cards:
        f0, _ = resolve(proj, c["at"])
        f1, hard = resolve(proj, c.get("until", "end"), f0 / FPS + 0.05)
        wins.append((f0, f1, hard))
    groups = fc.clusters(cards, [(a, b) for a, b, _ in wins])
    spans = {}
    for c, g in zip(cards, groups):
        r = fc.home(c)
        spans.setdefault(g, []).append(r)
    html = []
    for i, (c, (f0, f1, hard), g) in enumerate(zip(cards, wins, groups)):
        eid = f"k{i}"
        t0, t1 = f0 / FPS, f1 / FPS
        html.append(fc.card_html(c, eid, t0, t1))
        x, y, w, h = fc.home(c)
        gx, gw = fc.span(spans[g])
        fc.enter(tl, c, eid, t0, i + 1)
        label = c.get("title") or c.get("text") or c.get("eyebrow") or c.get("n")
        # the beat's hero is the cluster around the head: the region spans it at the entering card's height
        rx0 = max(0, min(gx, x - 230) if fc.side(c) == "left" else gx)      # it arrives from off its side
        rx1 = min(1080, max(gx + gw, x + w + 230) if fc.side(c) == "right" else gx + gw)
        tl.event(t0, "enter", f"card {label}", region=[rx0, y, rx1 - rx0, h], sel=f"#{eid}", show=True)
        snd = c.get("sfx", "auto")
        if snd != "off":
            if snd == "auto":
                snd = "pop_hi" if c.get("type") == "chip" else "swish"
            tl.cue(t0 + (0.1 if snd in ("swish", "whoosh") else 0.0), snd,
                   c.get("sfx_gain", -3.0 if snd in ("swish", "whoosh") else 0.0))
        last = {}
        for m in c.get("moves", []):
            tm = at_t(proj, m["at"], t0)
            fc.move(tl, eid, tm, m)
            last = m
            dx, dy = m.get("dx", 0), m.get("dy", 0)
            tl.event(tm, "move", f"{label} {m.get('what', 'moves')}",
                     region=[x + min(0, dx), y + min(0, dy), w + abs(dx), h + abs(dy)])
        body_events(proj, tl, c, eid, t0, x, y, w, h)
        if c.get("strike_at"):
            ts = at_t(proj, c["strike_at"], t0)
            tl.event(ts, "strike", f"strike {label}", region=[x - 10, y + h // 2 - 24, w + 20, 48])
            fc.strike_tumble(tl, c, eid, ts, last)
            fc.float_idle(tl, eid, t0 + fc.LAND, ts, i + 1)
            continue
        fc.float_idle(tl, eid, t0 + fc.LAND, t1, i + 1)
        if c.get("exit") == "cut":
            fc.hide(tl, eid, t1)
            tl.event(t1, "cut", f"card off at cut {c.get('until')}", region=[x, y, w, h], sel=f"#{eid}", show=False)
        elif t1 < proj.frames / FPS - 0.01:
            fc.exit_fly(tl, c, eid, t1)
    return "\n".join(html)


def body_events(proj, tl, c, eid, t0, x, y, w, h):
    """Things that happen INSIDE a card after it lands, each on its word: bars fill and tick, a slot opens and
    fills, the underline draws, the big value stamps, the status row lands and pulses."""
    land = t0 + 0.28
    for j, r in enumerate(c.get("rows", [])):
        tr = at_t(proj, r[2], t0) if len(r) > 2 else land + 0.08 * j
        tl.fromto(f"#{eid}b{j}", tr, {"scaleX": 0.04}, {"scaleX": 1}, 0.42, "expo.out")
        if len(r) > 2:
            tl.set(f"#{eid}t{j}", tr, {"visibility": "visible"})
            tl.raw(f"RRM.enter('drawOn',tl,document.querySelector('#{eid}t{j} path'),{tr:.5f},{{dur:0.22}});")
            tl.fromto(f"#{eid}t{j}", tr, {"scale": 0.5}, {"scale": 1}, 0.3, "back.out(2.2)")
    if c.get("ul_at"):
        tu = at_t(proj, c["ul_at"], t0)
        tl.fromto(f"#{eid}u", tu, {"scaleX": 0, "opacity": 1}, {"scaleX": 1}, 0.3, "power2.inOut")
    if c.get("slot"):
        s = c["slot"]
        ta = at_t(proj, s["at"], t0)
        tl.fromto(f"#{eid}s", ta, {"height": 0, "opacity": 0.35},
                  {"height": 46, "opacity": 1}, 0.34, "expo.out")
        tl.event(ta, "tick", "empty slot opens", region=[x + 20, y + h - 76, w - 40, 64])
        if s.get("fill_at"):
            tf = at_t(proj, s["fill_at"], ta)
            tl.to(f"#{eid}sq", tf, {"opacity": 0, "scale": 0.4}, 0.12, "power3.in")
            tl.set(f"#{eid}st", tf, {"visibility": "visible"})
            tl.raw(f"RRM.enter('drawOn',tl,document.querySelector('#{eid}st path'),{tf + 0.06:.5f},{{dur:0.24}});")
            tl.to(f"#{eid}s", tf, {"borderColor": "rgba(217,180,90,.95)", "backgroundColor": "rgba(217,180,90,.18)"}, 0.25, "power2.out")
    if c.get("value_at"):
        tv = at_t(proj, c["value_at"], t0)
        tl.set(f"#{eid}v", t0, {"opacity": 0})
        tl.set(f"#{eid}v", tv - 0.03, {"opacity": 1})
        # transform-only stamp (an opacity/filter layer inside the frosted card composites as a grey box)
        tl.fromto(f"#{eid}v .vv", tv - 0.03, {"scale": 1.75, "y": -12, "rotation": -4}, {"scale": 1, "y": 0, "rotation": 0},
                  0.24, "power4.out")
        tl.fromto(f"#{eid}g", tv, {"opacity": 0, "scale": 0.5}, {"opacity": 1, "scale": 1}, 0.5, "expo.out")
        tl.event(tv, "stamp", f"value {c.get('value')} stamps", region=[x + 120, y + 60, w - 240, 180])
        if c.get("value_sfx", "chime") != "off":
            tl.cue(tv, c.get("value_sfx", "chime"))
    if c.get("row_at"):
        fr = at_t(proj, c["row_at"], t0)
        tl.set(f"#{eid}r", t0, {"opacity": 0})
        tl.fromto(f"#{eid}r", fr, {"opacity": 0.4, "scale": 0.7, "y": 26, "filter": "blur(6px)"},
                  {"opacity": 1, "scale": 1, "y": 0, "filter": "blur(0px)"}, 0.34, "back.out(2.2)")
        tl.cue(fr, c.get("row_sfx", "pop_lo"))
        tl.event(fr, "tick", "status row lands", region=[x + 60, y + h - 96, w - 120, 86])
    for p in c.get("pulse_at", []):
        tp = at_t(proj, p, t0)
        tl.fromto(f"#{eid}d", tp, {"boxShadow": "0 0 0 0px rgba(122,30,46,.6)", "scale": 1.7},
                  {"boxShadow": "0 0 0 30px rgba(122,30,46,0)", "scale": 1}, 0.6, "expo.out")
        tl.fromto(f"#{eid}r", tp, {"scale": 1.09}, {"scale": 1}, 0.45, "back.out(2.2)")
        tl.event(tp, "tick", "status row pulses", region=[x + 60, y + h - 96, w - 120, 86])


# ---------------------------------------------------------------- title + HUD
def title_html(proj, tl, t):
    f1, _ = resolve(proj, t.get("until", "seg:" + proj.segments[1]["id"]))
    t1 = f1 / FPS
    tb = kit.box("title", 0, t1, True)
    y = t.get("y", 250)
    for cls, spec, how in (("t1", t.get("l1_at", 0.0), "maskPush"), ("t2", t.get("l2_at", 0.12), "maskPush"),
                           ("t3", t.get("l3_at", 0.3), "stamp")):
        if cls == "t3" and not t.get("l3"):
            continue
        ti = max(0.0, at_t(proj, spec) - 0.03) if isinstance(spec, str) else float(spec)
        if ti > 0.02:
            tl.set(f"#ttl .{cls}", 0, {"opacity": 0})
            tl.set(f"#ttl .{cls}", ti, {"opacity": 1})
        if how == "stamp":
            tl.raw(f"RRM.enter('stamp',tl,'#ttl .{cls}',{ti:.5f},{{from:1.9,blur:18,dur:0.24,rot0:-6,rot:-2}});")
        else:
            tl.raw(f"RRM.enter('maskPush',tl,document.querySelector('#ttl .{cls}'),{ti:.5f},{{dur:0.42}});")
        tl.event(ti + 0.02, "type", f"title {cls} in", region=[90, y, 900, 330])
    # it leaves up through its masks, 2x faster than it came, finishing on the cut frame
    tl.raw(f"['t1','t2'].forEach(function(c,i){{var e=document.querySelector('#ttl .'+c+' .rm-in');"
           f"if(e) tl.to(e,{{yPercent:-112,duration:0.16,ease:RRM.EASE.exit}},RRM.q({t1 - 0.2:.5f}+i*0.03));}});")
    tl.to("#ttl .t3", t1 - 0.18, {"opacity": 0, "y": -40, "filter": "blur(8px)"}, 0.16, "power3.in")
    tl.set("#ttl", t1, {"opacity": 0, "visibility": "hidden"})
    return (f'<div class="title" id="ttl" style="top:{y}px" {kit.box("card", 0, t1, False)}>'
            f'<span class="t1" {tb}>{esc(t["l1"])}</span><span class="t2" {tb}>{esc(t["l2"])}</span>'
            + (f'<span class="t3" {tb}>{esc(t["l3"])}</span>' if t.get("l3") else "") + '</div>')


def hud_html(proj, tl, h):
    """Step HUD: the dots pop in on the count, glide up to the top when the hook ends, the active step grows into a
    labelled pill on its word ("Number 1"), a finished step keeps a tinted dot."""
    n = int(h.get("n", 5))
    t0 = at_t(proj, h["at"]) - 0.07
    y, dock_y = int(h.get("y", 600)), int(h.get("dock_y", 236))
    acc = proj.colors["accent"]
    tb = kit.box("text", t0, proj.frames / FPS, True)
    dots = "".join(f'<div class="hd" id="hd{k + 1}"><span class="hn">{k + 1}</span><span class="hl" {tb}>'
                   f'{esc(h.get("label", "Step"))} {k + 1}</span></div>' for k in range(n))
    tl.set("#hud", t0, {"visibility": "visible", "opacity": 1})
    for k in range(n):
        tl.raw(f"RRM.enter('pop',tl,'#hd{k + 1}',{t0 + 0.04 * k:.5f},{{from:0.45,dur:0.34}});")
    tl.event(t0 + 0.1, "hud", "step HUD pops in", region=[360, y, 360, 62])
    if h.get("cue", "pop_hi") != "off":
        tl.cue(t0, h.get("cue", "pop_hi"), -4.0)
    if h.get("dock_at"):
        td = at_t(proj, h["dock_at"])
        tl.to("#hud", td, {"y": dock_y - y}, 0.5, "expo.out")
        tl.event(td, "hud", "HUD docks at the top", region=[330, dock_y, 420, y - dock_y + 64])
    prev = None
    for s in h.get("steps", []):
        ts = at_t(proj, s["at"]) - 0.03
        k = int(s["n"])
        if prev:
            tl.to(f"#hd{prev}", ts, {"width": 60, "backgroundColor": kit.rgba(acc, .16)}, 0.36, "expo.out")
            tl.to(f"#hd{prev} .hl", ts, {"opacity": 0}, 0.12, "power3.in")
            tl.to(f"#hd{prev} .hn", ts, {"color": acc}, 0.2, "power2.out")
        tl.to(f"#hd{k}", ts, {"width": s.get("w", 188), "backgroundColor": acc}, 0.42, "back.out(1.4)")
        tl.to(f"#hd{k} .hn", ts, {"color": "#ffffff"}, 0.2, "power2.out")
        tl.fromto(f"#hd{k} .hl", ts + 0.06, {"opacity": 0, "x": -14}, {"opacity": 1, "x": 0}, 0.3, "expo.out")
        tl.event(ts + 0.02, "hud", f"step {k} active", region=[300, dock_y - 6, 480, 76])
        if s.get("sfx", "pop_hi") != "off":
            tl.cue(ts, s.get("sfx", "pop_hi"), -3.0)
        prev = k
    return f'<div class="hud" id="hud" style="top:{y}px">{dots}</div>'


# ---------------------------------------------------------------- captions
def caption_top(proj, f0, f1, base=1280, cap=1375):
    """Under the chin, from the face track, with headroom for the camera (settle + punch grow the head about its
    chin by up to ~1.12x)."""
    ft = proj.facetrack["boxes"]
    bottoms = [v[1] + v[3] * 1.25 + 46 for k, v in ft.items() if f0 - 3 <= int(k) <= f1 + 3]
    return int(min(max(base, max(bottoms) if bottoms else base), cap))


def glow_captions(proj, tl, caps, punct=".,!?;:"):
    out, ws = [], proj.words_raw
    for i, w in enumerate(ws):
        s, e = float(w["start"]), float(w["end"])
        nxt = float(ws[i + 1]["start"]) if i + 1 < len(ws) else None
        end = nxt if (nxt is not None and nxt - e < 0.4) else e + 0.25
        end = min(end, proj.frames / FPS)
        f0, f1 = frame_of(s), frame_of(end)
        if f1 <= f0:
            f1 = f0 + 1
        text = w["text"].rstrip(punct)
        cid = f"w{i}"
        top = caption_top(proj, f0, f1)
        out.append(f'<div class="gcap" id="{cid}" style="top:{top}px" data-word="{i}">'
                   f'<span {kit.box("caption", f0 / FPS, f1 / FPS, True)}>{esc(text)}</span></div>')
        caps.append({"text": text, "f0": f0, "f1": f1, "words": [i]})
        tl.set(f"#{cid}", f0 / FPS, {"opacity": 0.55, "visibility": "visible"})
        tl.to(f"#{cid}", f0 / FPS, {"opacity": 1}, 0.1, "power1.out")
        tl.set(f"#{cid}", f1 / FPS, {"opacity": 0, "visibility": "hidden"})
    return "\n".join(out)


# ---------------------------------------------------------------- base video (grade, plus legacy baked words)
LAYER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>{ff}
html,body{{margin:0;background:transparent}}
.w{{position:absolute;left:0;top:{y}px;width:1080px;text-align:center;white-space:nowrap;font:900 {size}px/1 '{font}';
letter-spacing:{ls}em;color:{color};text-shadow:0 18px 50px rgba(29,18,20,.22),0 3px 8px rgba(29,18,20,.12)}}
.w span{{background:linear-gradient(180deg,{c1},{c2});-webkit-background-clip:text;background-clip:text;color:transparent}}
</style></head><body><div class="w"><span>{text}</span></div></body></html>"""


def plate_frames(proj):
    """Every 3rd frame of the un-zoomed takes (static camera): the clean plate behind the speaker."""
    zoom = {e["id"]: e.get("zoom", 1.0) for e in kit.jload(proj.p("edl.json"), [])}
    return [f for s in proj.segments if abs(zoom.get(s["id"], 1.0) - 1.0) < 0.01
            for f in range(s["frame"], s["frame"] + s["frames"], 3)]


def grade_of(proj):
    return proj.style.get("grade", {"lift": 0.03, "gamma": 0.9, "warm": 0.02, "sat": 1.05, "green": 0.99})


def prepare(proj, log=print):
    """Graded base plate (cached). Behind-head words are live by default; `"live": false` bakes one in (legacy)."""
    baked = [b for b in proj.style.get("behind", []) if b.get("live") is False]
    grade = grade_of(proj)
    key = hashlib.sha1(json.dumps([baked, grade, 8], sort_keys=True).encode()).hexdigest()[:10]
    out = proj.p("assets", f"base_{key}.mp4")
    if os.path.exists(out):
        return os.path.relpath(out, proj.dir)
    ff = kit.fontface(proj)
    layers = []
    acc = proj.colors["accent"]
    for i, b in enumerate(baked):
        page = proj.p("work", f"behind_{i}.html")
        with open(page, "w") as fh:
            fh.write(LAYER_HTML.format(ff=ff.replace("assets/fonts", proj.p("assets", "fonts")), y=b.get("y", 600),
                                       size=b.get("size", 320), font=proj.fonts["display"], ls=b.get("ls", -0.045),
                                       color=acc, c1=b.get("c1", "color-mix(in srgb," + acc + " 80%,#fff)"),
                                       c2=b.get("c2", acc), text=esc(b["text"])))
        png = kit.screenshot_html(page, proj.p("work", f"behind_{i}.png"))
        f0, _ = resolve(proj, b["at"])
        f1, _ = resolve(proj, b["until"], f0 / FPS + 0.1)
        layers.append({"png": png, "f0": f0, "f1": f1, "in": 11, "out": 8, "dy": 46, "s0": 1.06,
                       "cy": b.get("y", 600) + b.get("size", 320) * 0.5})
    import behind as bh
    for old in [x for x in os.listdir(proj.p("assets")) if x.startswith("base_")]:
        os.remove(proj.p("assets", old))
    bh.build_base(proj.p("assets", "aroll.mp4"), out, grade=grade, layers=layers,
                  matte=proj.p("assets", proj.style.get("matte", "aroll_matte.webm")),
                  plate_frames=plate_frames(proj) if layers else None, log=log)
    return os.path.relpath(out, proj.dir)


def mount_cam_layer(html, inner):
    """Put the live behind-head layer (#fcCam) right above the speaker inside the transition wrapper, and make it
    follow the engine camera key for key (same transform origin, scale, offset, rotation, rack blur)."""
    if not inner:
        return html
    layer = f'<div id="fcCam" data-layout-allow-overflow><div id="fcDollyB" class="fc-dolly">{inner}</div></div>'
    i = html.find('id="mvCam"')
    if i >= 0:
        j = html.find("</video></div>", i)
        if j < 0:
            raise SystemExit("floating-cards: could not find the camera wrapper to mount the behind-head layer")
        j += len("</video></div>")
        return (html[:j] + layer + html[j:]).replace('"#mvCam"', '"#mvCam,#fcCam"')
    j = html.find("</video>")             # motion off: no camera, the layer sits right on the plate
    return html[:j + 8] + layer + html[j + 8:]


# ---------------------------------------------------------------- compose
def compose(project_dir, log=print):
    proj = kit.Project(project_dir)
    proj.frames = sum(s["frames"] for s in proj.segments)
    proj.facetrack = kit.jload(proj.p("work", "facetrack.json"))
    cfg = proj.style
    base = prepare(proj, log)
    tl = kit.TL()
    live = [b for b in cfg.get("behind", []) if b.get("live", True)]
    bh_html, bh_items, bh_wins = fc_behind.build(proj, tl, resolve, grade_of(proj), plate_frames(proj) if live else None, log)
    for b in [b for b in cfg.get("behind", []) if b.get("live") is False]:
        f0, _ = resolve(proj, b["at"])
        tl.cue(f0 / FPS, b.get("sfx", "thump"))
        tl.event(f0 / FPS, "enter", f"behind-head word {b['text']}", region=[60, b.get("y", 600), 960, b.get("size", 320)])
    body = [f'<video id="aroll" src="{base}" playsinline data-start="0" data-duration="{kit.duration_str(proj.frames)}" '
            f'data-track-index="0" data-has-audio="true"></video>', '<div class="layer" id="cards">']
    if cfg.get("title"):
        body.append(title_html(proj, tl, cfg["title"]))
    if cfg.get("hud"):
        body.append(hud_html(proj, tl, cfg["hud"]))
    body.append(place_cards(proj, tl, cfg.get("cards", [])))
    body.append("</div>")
    caps = []
    body.append(glow_captions(proj, tl, caps))
    dcfg = cfg.get("dolly", {}) if (proj.motion and proj.motion.get("level") != "simple") else False
    dolly = fc_dolly.plan(proj, dcfg)
    tl.js.extend(fc_dolly.js(dolly))
    f = proj.fonts
    html = kit.build_html(
        title=proj.pj.get("title", "Floating cards"), css=fc_style.css(proj) + fc_behind.css(proj) + fc_dolly.css(),
        fontface=kit.fontface(proj, italic=[proj.fonts.get("serif", proj.fonts["display"])]),
        fonts_load=[f'900 100px "{f["display"]}"', f'800 46px "{f["display"]}"', f'500 27px "{f["body"]}"',
                    f'italic 700 100px "{f.get("serif", f["display"])}"'],
        total=kit.duration_str(proj.frames), body="\n".join(body), tween_js="\n".join("  " + j for j in tl.js),
        gsap_src=kit.ensure_gsap(proj.dir))
    html = mount_cam_layer(html, bh_html)
    if dolly:
        html = fc_dolly.wrap_plate(html)
    with open(proj.p("index.html"), "w") as fh:
        fh.write(html)
    kit.write_hf_config(proj.dir)
    plan = kit.M.load_plan(proj.dir)
    if plan is not None and bh_items:            # QA behind_head + transition_budget read these
        plan["behind"], plan["cutout_windows"] = bh_items, bh_wins
        kit.M.write_plan(proj.dir, plan)
    meta = {"template": "floating-cards", "frames": proj.frames, "base_video": base, "voice_src": "assets/aroll.mp4",
            "facetrack": "work/facetrack.json", "events": tl.events, "cues": tl.cues,
            "captions": {"mode": "word", "strip": ".,!?;:"}, "caption_list": caps,
            "dolly": dolly, "loop": cfg.get("loop", {"t0": 12.0}), "poster": cfg.get("poster", {"t": 24.6})}
    kit.jsave(proj.p("work", "meta.json"), meta)
    log(f"compose: {proj.frames} frames, {len(tl.events)} events, {len(tl.cues)} sfx cues")
    return meta


if __name__ == "__main__":
    compose(sys.argv[1])
