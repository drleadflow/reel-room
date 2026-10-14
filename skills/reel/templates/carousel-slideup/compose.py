#!/usr/bin/env python3
"""Carousel Slide-up template: a 10-14 s condensed cut (one reframed shot of the speaker, face high), a serif title
for the whole reel, and cream carousel cards that rise from the bottom one after another on their words. No captions:
the title and the cards carry the text. Voice kept.

Motion v2 phase 3 (physical cards):
  - the title stamps in on frame 0, its second line pushes up on its word, the accent word slams in on its word and
    the leading number pulses when it is spoken
  - each card rises with momentum (3D tilt, motion blur) and overshoots into place, then floats while it holds
  - the previous card tilts back in 3D and falls away as the next one rises
  - card contents build on their words: the copy line blurs in, mini rows fill with their values counting up, the
    week grid ticks off week by week to the picked deadline, which stamps with its flag
  - the card stack sits on its own depth plane: it follows the camera at a fraction (engine motion parallax), so the
    shot moves behind the cards

  compose.py <project>     cut (cached) -> index.html + work/meta.json   (run through stylekit/build.py)

Content lives in project.json "style_cfg": cut (see cut.py), title, cards[], loop, poster. Colours/fonts: brand.json.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
sys.path.insert(0, HERE)
import kit  # noqa: E402
from kit import FPS, esc, frame_of  # noqa: E402

CARD = {"x": 100, "y": 918, "w": 880, "h": 528}
STACK_ORIGIN = (540, 760)     # the card plane scales about the face area, like the camera
PARALLAX_K = 0.35             # the card plane follows the camera at 35 %: the shot moves behind the cards
PERSP = 1400


def css(proj):
    c, f = proj.colors, proj.fonts
    ink, acc, gold, bg = c["ink"], c["accent"], c["highlight"], c["bg"]
    serif = f.get("serif", f["display"])
    return f"""
:root{{--ink:{ink};--acc:{acc};--gold:{gold};--bg:{bg};--fd:{kit.fam(f['display'])};--fb:{kit.fam(f['body'])};
--fs:'{serif}',Georgia,serif;--soft:color-mix(in srgb,{ink} 60%,{bg});--line:color-mix(in srgb,{ink} 10%,transparent)}}
html,body{{margin:0;padding:0;background:#000}}
*{{box-sizing:border-box}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:#000;font-family:var(--fb);color:var(--ink)}}
#aroll{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover;z-index:1}}
.ttl{{position:absolute;left:0;width:1080px;z-index:6;display:flex;flex-direction:column;align-items:center;text-align:center}}
.ttl>span{{display:block;font:700 84px/1.06 var(--fs);letter-spacing:-.012em;color:var(--ink);white-space:nowrap;
  text-shadow:0 0 28px rgba(255,255,255,.7),0 2px 2px rgba(255,255,255,.4)}}
.ttl b{{display:inline-block;font-weight:700;transform-origin:50% 70%}}
.ttl em{{display:inline-block;font-style:italic;color:var(--acc);transform-origin:30% 70%}}
#ccStack{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:8;transform-origin:{STACK_ORIGIN[0]}px {STACK_ORIGIN[1]}px}}
.cc{{position:absolute;left:{CARD['x']}px;top:{CARD['y']}px;width:{CARD['w']}px;height:{CARD['h']}px;z-index:8;border-radius:40px;
  background:var(--bg);padding:40px 52px 34px;display:flex;flex-direction:column;opacity:0;visibility:hidden;
  box-shadow:0 34px 80px {kit.rgba(ink, .30)},0 8px 22px {kit.rgba(ink, .14)},inset 0 1px 0 #fff}}
.cc .hd{{display:flex;justify-content:space-between;align-items:center;font:800 26px/1 var(--fb);letter-spacing:.22em;color:var(--acc)}}
.cc .hd .pg{{font:600 26px/1 var(--fb);letter-spacing:.06em;color:var(--soft)}}
.cc .tt{{font:900 100px/1 var(--fd);letter-spacing:-.03em;word-spacing:.08em;text-transform:uppercase;color:var(--acc);margin-top:22px;white-space:nowrap}}
.cc .cp{{font:500 36px/1.15 var(--fb);color:var(--soft);margin-top:14px;white-space:nowrap;opacity:0}}
.cc .mini{{margin-top:24px;background:#fff;border-radius:22px;border:1.5px solid var(--line);padding:14px 26px;
  box-shadow:0 6px 18px {kit.rgba(ink, .06)}}}
.cc .mr{{display:flex;align-items:center;height:48px;gap:18px;font:600 28px/1 var(--fb);color:var(--ink);opacity:.2}}
.cc .mr+.mr{{border-top:1.5px solid var(--line)}}
.cc .mr .nm{{width:250px;white-space:nowrap}}
.cc .mr .bar{{flex:1;height:12px;border-radius:7px;background:{kit.rgba(ink, .1)};position:relative;overflow:hidden}}
.cc .mr .bar b{{position:absolute;left:0;top:0;bottom:0;border-radius:7px;background:var(--acc);transform:scaleX(0);transform-origin:0 50%}}
.cc .mr .v{{width:66px;text-align:right;font:800 28px/1 var(--fd);color:var(--acc);font-variant-numeric:tabular-nums}}
.cc .weeks{{margin-top:30px;display:grid;grid-template-columns:repeat(6,1fr);gap:14px}}
.cc .wk{{height:74px;border-radius:16px;background:#fff;border:1.5px solid var(--line);display:flex;align-items:center;justify-content:center;
  font:800 26px/1 var(--fd);color:color-mix(in srgb,{ink} 40%,{bg});position:relative;overflow:visible}}
.cc .wk .ok{{position:absolute;inset:-1.5px;border-radius:16px;background:{kit.rgba(acc, .2)};border:2px solid {kit.rgba(acc, .55)};
  display:flex;align-items:center;justify-content:center;color:var(--acc);opacity:0}}
.cc .wk .on{{position:absolute;inset:-1.5px;border-radius:16px;background:var(--acc);color:#fff;display:flex;align-items:center;justify-content:center;opacity:0;
  box-shadow:0 0 0 6px {kit.rgba(gold, .45)}}}
.cc .flag{{position:absolute;right:52px;top:92px;padding:14px 24px 15px;border-radius:999px;background:var(--gold);color:var(--ink);
  font:800 30px/1 var(--fd);letter-spacing:.06em;text-transform:uppercase;opacity:0;box-shadow:0 10px 24px {kit.rgba(gold, .45)}}}
.cc .ft{{margin-top:auto;display:flex;justify-content:space-between;align-items:center;font:800 20px/1 var(--fb);letter-spacing:.3em;color:var(--acc)}}
.cc .ft .ar{{font:600 30px/1 var(--fb);letter-spacing:0;color:var(--soft)}}
"""


def card_html(c, i, n_total, t0, t1):
    tb = kit.box("text", t0, t1, True)
    body = ""
    if c.get("copy"):
        body += f'<div class="cp" id="cc{i}cp" {tb}>{esc(c["copy"])}</div>'
    if c.get("rows"):
        rows = "".join(f'<div class="mr" id="cc{i}r{j}"><span class="nm" {tb}>{esc(r[0])}</span>'
                       f'<span class="bar"><b id="cc{i}b{j}" style="width:{r[1]}%"></b></span>'
                       f'<span class="v" id="cc{i}v{j}" {tb}>0</span></div>' for j, r in enumerate(c["rows"]))
        body += f'<div class="mini">{rows}</div>'
    if c.get("weeks"):
        wk = c["weeks"]
        cells = "".join(f'<div class="wk"><span {tb}>W{k}</span>'
                        + (f'<span class="on" id="cc{i}on">W{k}</span>' if k == wk["pick"] else f'<span class="ok">W{k}</span>')
                        + '</div>' for k in range(1, wk["n"] + 1))
        body += f'<div class="weeks" id="cc{i}wk">{cells}</div>'
        if wk.get("flag"):
            body += f'<div class="flag" id="cc{i}fl" {tb}>{esc(wk["flag"])}</div>'
    return (f'<div class="cc" id="cc{i}" {kit.box("card", t0, t1, False)}>'
            f'<div class="hd"><span {tb}>{esc(c["eyebrow"])}</span><span class="pg" {tb}>{i + 1} / {esc(c.get("of", n_total))}</span></div>'
            f'<div class="tt" data-fit="776,60" {tb}>{esc(c["title"])}</div>{body}'
            f'<div class="ft"><span {tb}>{esc(c.get("footer", ""))}</span><span class="ar">&rarr;</span></div></div>')


# ----------------------------------------------------------------------------- title
def title_html(t, total_t):
    """Line 1 with its leading number in its own span (it pulses when spoken), line 2 with the accent word."""
    m = re.match(r"^(\d+)(\s.*)$", t["l1"])
    l1 = (f'<b id="ttn">{esc(m.group(1))}</b>{esc(m.group(2))}' if m else esc(t["l1"]))
    acc = f' <em id="tte">{esc(t["accent"])}</em>' if t.get("accent") else ""
    return (f'<div class="ttl" style="top:{t.get("y", 236)}px" {kit.box("card", 0, total_t, False)}>'
            f'<span id="tt1" {kit.box("title", 0, total_t, True)}>{l1}</span>'
            f'<span id="tt2" {kit.box("title", 0, total_t, True)}>{esc(t["l2"])}{acc}</span></div>'), bool(m)


def title_motion(proj, tl, t, has_num):
    """Stamp on frame 0 (already faintly there), line 2 pushes up on its word, the accent word slams in on its word,
    the leading number pulses when it is spoken."""
    y = t.get("y", 236)
    reg1, reg2 = [140, y - 10, 800, 100], [140, y + 80, 800, 100]
    tl.fromto("#tt1", 0, {"opacity": 0.35, "scale": 1.16, "y": -8, "filter": "blur(10px)"},
              {"opacity": 1, "scale": 1, "y": 0, "filter": "blur(0px)"}, 0.32, "power4.out")
    t2 = proj.at(t["l2_at"]) - 0.05 if t.get("l2_at") else 0.45
    tl.set("#tt2", 0, {"opacity": 0})
    tl.fromto("#tt2", t2, {"opacity": 0, "yPercent": 55, "filter": "blur(8px)"},
              {"opacity": 1, "yPercent": 0, "filter": "blur(0px)"}, 0.4, "expo.out")
    tl.event(t2, "type", "title line 2", region=reg2)
    if t.get("accent"):
        ta = max(t2 + 0.3, proj.at(t["accent_at"]) - 0.03) if t.get("accent_at") else t2 + 0.5
        tl.set("#tte", 0, {"opacity": 0})
        tl.fromto("#tte", ta, {"opacity": 0, "scale": 2.3, "rotation": -9, "filter": "blur(16px)"},
                  {"opacity": 1, "scale": 1, "rotation": 0, "filter": "blur(0px)"}, 0.24, "power4.out")
        tl.event(ta, "stamp", "title accent word", region=[600, y + 80, 340, 100])
        tl.cue(ta, "pop", -6.0)
    if has_num and t.get("num_at"):
        tn = proj.at(t["num_at"]) - 0.03
        tl.fromto("#ttn", tn, {"scale": 1.5, "color": kit_color(proj, "accent")}, {"scale": 1, "color": kit_color(proj, "ink")},
                  0.42, "power4.out")
        tl.event(tn, "stamp", "title number pulse", region=reg1[:2] + [260, 100])


def kit_color(proj, k):
    return proj.colors.get(k, "#7A1E2E")


# ----------------------------------------------------------------------------- cards
def card_in(tl, sel, t0):
    """Rises with momentum: tilted back in 3D and motion-blurred, the tilt overshoots and swings back (the slot itself
    is overshot by only ~1 %, so the card never climbs onto the chin)."""
    tl.set(sel, t0, {"visibility": "visible", "opacity": 1})
    tl.fromto(sel, t0, {"y": 980, "scale": 0.94, "filter": "blur(10px)"}, {"y": 0, "scale": 1, "filter": "blur(0px)"},
              0.7, "back.out(0.6)")
    tl.fromto(sel, t0, {"rotationX": -26, "rotation": 3.5, "transformPerspective": PERSP, "transformOrigin": "50% 100%"},
              {"rotationX": 0, "rotation": 0, "transformPerspective": PERSP, "transformOrigin": "50% 100%"}, 0.8, "back.out(2.2)")


def card_out(tl, sel, t1):
    """Tilts back in 3D and falls away as the next card rises."""
    tl.to(sel, t1, {"y": 340, "rotationX": 58, "z": -220, "scale": 0.9, "opacity": 0, "filter": "blur(6px)",
                    "transformPerspective": PERSP, "transformOrigin": "50% 100%"}, 0.5, "power3.in")
    tl.set(sel, t1 + 0.5, {"visibility": "hidden"})


def card_float(tl, sel, t0, t1, seed):
    """Idle float while the card holds (x and rotation only: the entrance owns y)."""
    span, period = t1 - t0, 1.7
    if span < period:
        return
    reps = max(0, int(span / period) - 1)
    k = 1 if seed % 2 == 0 else -1
    tl.raw(f'tl.fromTo("{sel}",{{x:0,rotation:0}},{{x:{-5 * k},rotation:{0.5 * k},duration:{period},ease:"sine.inOut",'
           f'yoyo:true,repeat:{reps},immediateRender:false}},{kit.snap(t0)});')


def card_contents(proj, tl, c, i, t0):
    lo = t0 - 0.05
    if c.get("copy"):
        tc = proj.at(c.get("copy_at"), lo) if isinstance(c.get("copy_at"), str) else t0 + 0.25
        tl.fromto(f"#cc{i}cp", tc, {"opacity": 0, "x": -24, "filter": "blur(8px)"}, {"opacity": 1, "x": 0, "filter": "blur(0px)"}, 0.34)
        tl.event(tc, "type", f"card {i + 1} copy", region=[CARD["x"] + 52, CARD["y"] + 200, 440, 44])
    for j, r in enumerate(c.get("rows", [])):
        tr = proj.at(r[2], lo) if len(r) > 2 else t0 + 0.3 + 0.15 * j
        reg = [CARD["x"] + 78, CARD["y"] + 284 + 50 * j, 724, 46]
        tl.fromto(f"#cc{i}r{j}", tr, {"opacity": 0.45, "x": -10}, {"opacity": 1, "x": 0}, 0.28, "expo.out")
        tl.fromto(f"#cc{i}b{j}", tr, {"scaleX": 0}, {"scaleX": 1}, 0.7, "expo.out")
        tl.fromto(f"#cc{i}v{j}", tr, {"innerText": 0}, {"innerText": int(r[1]), "snap": {"innerText": 1}}, 0.7, "expo.out")
        tl.event(tr, "fill", f"card {i + 1} row {r[0]} fills", region=reg)
    if c.get("weeks"):
        wk = c["weeks"]
        tp = proj.at(wk["at"], lo)
        n_ok = wk["n"] - 1 if wk["pick"] == wk["n"] else wk["n"]
        tk0 = t0 + 0.42
        step = max(0.03, min(0.09, (tp - 0.12 - tk0) / max(1, n_ok)))
        tl.raw(f'tl.fromTo("#cc{i}wk .ok",{{opacity:0,scale:0.6}},{{opacity:1,scale:1,duration:0.18,ease:"expo.out",'
               f'stagger:{step:.3f},immediateRender:false}},{kit.snap(tk0)});')
        tl.event(tk0, "tick", f"card {i + 1} weeks tick off", region=[CARD["x"] + 52, CARD["y"] + 218, 118, 74])  # W1
        tl.fromto(f"#cc{i}on", tp, {"opacity": 0, "scale": 1.7, "rotation": -8, "filter": "blur(8px)"},
                  {"opacity": 1, "scale": 1, "rotation": 0, "filter": "blur(0px)"}, 0.24, "power4.out")
        if wk.get("flag"):
            tl.fromto(f"#cc{i}fl", tp + 0.1, {"opacity": 0, "scale": 0.5, "y": 10}, {"opacity": 1, "scale": 1, "y": 0}, 0.34, "back.out(2.2)")
        tl.event(tp, "stamp", f"card {i + 1} deadline pick", region=[CARD["x"] + 690, CARD["y"] + 368, 150, 90])
        tl.cue(tp, "pop", -2.0)


def compose(project_dir, log=print):
    proj = kit.Project(project_dir)
    import cut
    cut.build(proj, log)
    proj = kit.Project(project_dir)  # reload the condensed words/segments
    if proj.motion is not None and not proj.motion.get("parallax"):
        proj.motion["parallax"] = [{"sel": "#ccStack", "k": PARALLAX_K}]
    proj.frames = sum(s["frames"] for s in proj.segments)
    cfg = proj.style
    tl = kit.TL()
    seg = {s["id"]: s for s in proj.segments}
    total_t = proj.frames / FPS
    t = cfg["title"]
    ttl, has_num = title_html(t, total_t)
    body = [f'<video id="aroll" src="assets/aroll.mp4" playsinline data-start="0" data-duration="{kit.duration_str(proj.frames)}" '
            f'data-track-index="0" data-has-audio="true"></video>', ttl]
    title_motion(proj, tl, t, has_num)
    cards = cfg["cards"]
    starts = [seg[c["at"][4:]]["frame"] if c["at"].startswith("seg:") else frame_of(proj.at(c["at"])) for c in cards]
    stack = []
    for i, c in enumerate(cards):
        f0 = starts[i]
        f1 = starts[i + 1] if i + 1 < len(cards) else proj.frames
        t0, t1 = f0 / FPS, f1 / FPS
        stack.append(card_html(c, i, c.get("of", len(cards)), t0, t1 + (0.5 if i + 1 < len(cards) else 0)))
        sel = f"#cc{i}"
        card_in(tl, sel, t0)
        tl.event(t0, "enter", f"card {i + 1} rises", region=[CARD["x"], 1300, CARD["w"], 600], sel=sel, show=True)
        tl.cue(t0, "swish")
        card_float(tl, sel, t0 + 0.75, t1 - 0.05, i)
        if i + 1 < len(cards):
            card_out(tl, sel, t1)
        card_contents(proj, tl, c, i, t0)
    body.append(f'<div id="ccStack" data-layout-allow-overflow>{"".join(stack)}</div>')
    f = proj.fonts
    serif = f.get("serif", f["display"])
    html = kit.build_html(
        title=proj.pj.get("title", "Carousel slide-up"), css=css(proj), fontface=kit.fontface(proj, italic=[serif]),
        fonts_load=[f'700 84px "{serif}"', f'italic 700 84px "{serif}"', f'900 100px "{f["display"]}"',
                    f'800 26px "{f["body"]}"', f'500 36px "{f["body"]}"'],
        total=kit.duration_str(proj.frames), body="\n".join(body), tween_js="\n".join("  " + j for j in tl.js),
        gsap_src=kit.ensure_gsap(proj.dir))
    with open(proj.p("index.html"), "w") as fh:
        fh.write(html)
    kit.write_hf_config(proj.dir)
    meta = {"template": "carousel-slideup", "frames": proj.frames, "voice_src": "assets/voice.wav",
            "facetrack": "work/facetrack.json", "events": tl.events, "cues": tl.cues, "captions": {"mode": "none"},
            "caption_list": [], "loop": cfg.get("loop", {"t0": 4.2}), "poster": cfg.get("poster", {"t": 7.0})}
    kit.jsave(proj.p("work", "meta.json"), meta)
    log(f"compose: {proj.frames} frames ({proj.frames / FPS:.2f} s), {len(tl.events)} events, {len(tl.cues)} cues")
    return meta


if __name__ == "__main__":
    compose(sys.argv[1])
