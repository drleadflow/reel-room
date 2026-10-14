#!/usr/bin/env python3
"""Editorial UI template: the speaker cut out onto a solid brand-colour set on the hook and every punchline, huge
serif headlines BEHIND the head, small subtitles in a dark pill at chest height, cream UI cards (status pill, AI prompt
pill that types then turns into a DONE chip, panel card with ticks, magazine cover frame, countdown, kit cards from the
plan compiler: kitcards.py) and cut-backs to the real room between punchlines.

  compose.py <project>     bake the set layer (bake.py, cached) then write index.html + work/meta.json
  normally run through:    make.py <project> --out <dir> (lint, render, SFX mix + -14 LUFS master, loop, poster, QA)

Config: project.json "editorial" (README.md). Colours and fonts: brand.json via etheme.py.
"""
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan as _plan  # noqa: E402  (puts stylekit on sys.path)
import kit  # noqa: E402
from kit import FPS, esc  # noqa: E402
import etheme as theme  # noqa: E402
import layers  # noqa: E402
import takeover as _tko  # noqa: E402  (Motion v2 takeover scene)
import kitcards  # noqa: E402  (plan-compiler cards: everyday editorial beats, kit pieces, library heroes)
import sounds  # noqa: E402,F401  (registers the extra synthesized UI sounds: key, shutter, tick)

CHECK = ('<svg viewBox="0 0 24 24" width="{s}" height="{s}"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" '
         'stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ARROW = ('<svg viewBox="0 0 24 24" width="30" height="30"><path d="M12 19V6M6 11.5L12 5.5l6 6" fill="none" '
         'stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
H_EST = {"status": 84, "prompt": 108, "panel_head": 92, "panel_row": 78, "countdown": 186, "cover": 54}
# Motion v2 card entrance: a 3D fly-in (tilted back, blurred, from below) that lands with expo.out. Starts at 0.5
# opacity so the card is already there on its own frame (QA switch check), the tilt and blur do the work.
FLY_TRAVEL = 110        # the switch-check region of a flying card includes its travel (it is still landing on frame N)
FLY = {"opacity": 0.5, "y": FLY_TRAVEL, "rotationX": -62, "scale": 0.9, "filter": "blur(14px)", "transformPerspective": 1100}




# ------------------------------------------------------------------ css
def css(tok, cfg):
    sub = cfg["subtitle"]
    sfam = theme.serif(tok) if sub.get("font") == "serif" else theme.ui(tok)
    ink, cream, gold, pill, setc, flag = tok["ink"], tok["cream"], tok["gold"], tok["pill"], tok["set"], tok["flag"]
    return f"""
:root{{--ink:{ink};--cream:{cream};--gold:{gold};--set:{setc};--flag:{flag};--fs:{theme.serif(tok)};--fu:{theme.ui(tok)};--fm:{theme.mono(tok)}}}
html,body{{margin:0;padding:0;background:#000}}
*{{box-sizing:border-box}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:{setc};font-family:var(--fu);color:var(--ink)}}
#base{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover;z-index:1}}
.layer{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:5;pointer-events:none}}
.row{{position:absolute;left:0;width:1080px;display:flex;justify-content:center}}
.el{{opacity:0;visibility:hidden}}
.abs{{position:absolute}}
/* subtitles */
.sub{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;z-index:20;opacity:0;visibility:hidden}}
.sub .p{{font:600 {sub['px']}px/1.12 {sfam};letter-spacing:-.005em;color:{theme.rgba(cream, sub['dim'])};
  background:{theme.rgba(pill, .86)};padding:12px 24px 14px;border-radius:20px;white-space:nowrap;
  box-shadow:0 10px 30px {theme.rgba(pill, .28)}}}
.sub .p b{{font-weight:inherit}}
.sub.compact .p{{font-size:{round(sub['px'] * 0.88)}px;padding:9px 20px 11px;border-radius:17px}}
/* status chip */
.chip{{display:flex;align-items:center;justify-content:center;gap:16px;height:84px;min-width:700px;padding:0 34px 0 28px;border-radius:999px;white-space:nowrap;
  background:{cream};box-shadow:0 18px 44px {theme.rgba(pill, .30)},0 2px 6px {theme.rgba(pill, .16)},inset 0 0 0 1.5px rgba(255,255,255,.7)}}
.chip .dot{{width:14px;height:14px;border-radius:50%;flex:none}}
.dot.gold{{background:{gold};box-shadow:0 0 0 5px {theme.rgba(gold, .22)}}}
.dot.flag{{background:{flag};box-shadow:0 0 0 5px {theme.rgba(flag, .2)}}}
.dot.ink{{background:{setc};box-shadow:0 0 0 5px {theme.rgba(setc, .18)}}}
.chip .lb{{font:600 25px/1 var(--fm);letter-spacing:.14em;color:{ink}}}
.chip .sp{{font:500 26px/1 var(--fu);color:{theme.rgba(ink, .35)}}}
.chip .tx{{font:600 34px/1 var(--fu);letter-spacing:-.01em;color:{theme.rgba(ink, .78)}}}
.chip .tx s{{text-decoration:none;visibility:hidden}}
.chip .ok{{width:40px;height:40px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;background:{setc};color:{cream}}}
/* prompt pill */
.prompt{{position:relative;width:920px;height:108px;border-radius:30px;background:{cream};padding:16px 112px 0 34px;
  box-shadow:0 22px 52px {theme.rgba(pill, .32)},0 2px 8px {theme.rgba(pill, .16)},inset 0 0 0 1.5px rgba(255,255,255,.7)}}
.prompt .lb{{font:600 19px/1 var(--fm);letter-spacing:.16em;color:{theme.rgba(setc, .8)};display:flex;gap:12px;align-items:center}}
.prompt .lb .st{{color:{theme.rgba(ink, .4)}}}
.prompt .tx{{margin-top:12px;font:500 36px/1.1 var(--fu);letter-spacing:-.01em;color:{ink};white-space:nowrap;overflow:hidden}}
.prompt .tx s{{text-decoration:none;display:none}}
.prompt.nolabel{{padding-top:0;display:flex;align-items:center}}
.prompt.nolabel .lb{{position:absolute;left:34px;top:12px;font-size:16px}}
.prompt.nolabel .tx{{margin-top:0}}
.prompt .caret{{display:inline-block;width:3px;height:36px;margin-left:2px;vertical-align:-6px;background:{setc}}}
.prompt .go{{position:absolute;right:20px;top:20px;width:68px;height:68px;border-radius:50%;background:{setc};color:{cream};
  display:flex;align-items:center;justify-content:center}}
.prompt .dots{{display:inline-flex;gap:6px}} .prompt .dots i{{width:7px;height:7px;border-radius:50%;background:{theme.rgba(ink, .45)};opacity:.25}}
/* panel card */
.panel{{width:880px;border-radius:32px;background:{cream};padding:28px 36px 22px;
  box-shadow:0 26px 60px {theme.rgba(pill, .32)},0 2px 8px {theme.rgba(pill, .16)},inset 0 0 0 1.5px rgba(255,255,255,.7)}}
.panel .ph{{display:flex;justify-content:space-between;align-items:center;font:600 21px/1 var(--fm);letter-spacing:.18em;color:{theme.rgba(setc, .85)};
  padding-bottom:18px;border-bottom:2px solid {theme.rgba(ink, .1)}}}
.panel .ph i{{font-style:normal;color:{theme.rgba(ink, .35)}}}
.panel .pr{{position:relative;display:flex;align-items:center;gap:20px;height:78px;padding:0 14px;margin:0 -14px;border-radius:16px}}
.panel .pr + .pr{{border-top:1.5px solid {theme.rgba(ink, .07)}}}
.panel .pr .hl{{position:absolute;inset:6px 0;border-radius:14px;background:{theme.rgba(gold, .32)};opacity:0}}
.panel .ck{{position:relative;width:40px;height:40px;border-radius:50%;flex:none;border:3px solid {theme.rgba(ink, .22)};color:{cream}}}
.panel .ck .f{{position:absolute;inset:-3px;border-radius:50%;background:{setc};display:flex;align-items:center;justify-content:center;opacity:0}}
.panel .pt{{position:relative;font:600 35px/1 var(--fu);letter-spacing:-.012em;color:{ink};white-space:nowrap}}
/* cover frame */
.cover{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.cover .bd{{position:absolute;left:44px;top:232px;width:992px;height:1230px;border:2px solid {theme.rgba(gold, .9)}}}
.cover .bd2{{position:absolute;left:54px;top:242px;width:972px;height:1210px;border:1px solid {theme.rgba(gold, .45)}}}
.cover .kk{{position:absolute;left:72px;right:72px;top:258px;display:flex;justify-content:space-between;
  font:600 23px/1 var(--fu);letter-spacing:.24em;color:{gold};white-space:nowrap}}
.cover .bc{{position:absolute;left:76px;top:1350px;width:176px;height:92px;background:{cream};padding:10px 12px 0;border-radius:3px}}
.cover .bc .bars{{display:flex;align-items:stretch;height:52px;gap:0}}
.cover .bc .bars i{{display:block;background:{ink};height:100%}}
.cover .bc .nm{{font:500 13px/1 var(--fm);letter-spacing:.06em;white-space:nowrap;color:{ink};margin-top:7px;text-align:center}}
.flash{{position:absolute;inset:0;background:{cream};opacity:0;visibility:hidden;z-index:30}}
/* countdown */
.cd{{width:720px;height:186px;border-radius:30px;background:{theme.rgba(pill, .94)};padding:22px 34px 0;
  box-shadow:0 24px 60px {theme.rgba(pill, .45)},inset 0 0 0 1.5px {theme.rgba(gold, .55)}}}
.cd .cl{{display:flex;justify-content:space-between;font:600 20px/1 var(--fm);letter-spacing:.18em;color:{gold}}}
.cd .cl i{{font-style:normal;display:flex;align-items:center;gap:10px;color:{theme.rgba(cream, .55)}}}
.cd .cl i b{{width:10px;height:10px;border-radius:50%;background:{flag}}}
.cd .dg{{position:relative;height:88px;margin-top:16px}}
.cd .v{{position:absolute;left:0;right:0;top:0;display:flex;justify-content:space-between;visibility:hidden}}
.cd .u{{display:flex;flex-direction:column;align-items:center;width:130px}}
.cd .u b{{font:500 66px/1 var(--fm);letter-spacing:-.02em;color:{cream}}}
.cd .u i{{font:600 14px/1 var(--fm);font-style:normal;letter-spacing:.2em;color:{theme.rgba(cream, .5)};margin-top:8px}}
.cd .c{{font:500 50px/66px var(--fm);color:{theme.rgba(cream, .35)}}}
"""


# ------------------------------------------------------------------ pieces
def pop_in(tl, sel, f, frm=None, dur=0.5, ease="expo.out"):
    frm = dict(frm or FLY)
    to = {"opacity": 1, "y": 0, "scale": 1}
    for k in ("rotationX", "rotationY", "x"):
        if k in frm:
            to[k] = 0
    if "filter" in frm:
        to["filter"] = "blur(0px)"
    if "transformPerspective" in frm:
        to["transformPerspective"] = frm["transformPerspective"]
    tl.set(sel, f / FPS, {"visibility": "visible"})
    tl.fromto(sel, f / FPS, frm, to, dur, ease)


def hide(tl, sel, f):
    tl.set(sel, f / FPS, {"opacity": 0, "visibility": "hidden"})


def status_html(c, y, tok):
    tone = c.get("tone", "gold")
    chars = "".join(f'<s id="{c["id"]}t{i}">{esc(ch) if ch != " " else "&nbsp;"}</s>' for i, ch in enumerate(c["text"]))
    return (f'<div class="row" style="top:{y}px"><div class="el chip" id="{c["id"]}" {kit.box("card", c["f0"] / FPS, c["f1"] / FPS)}>'
            f'<i class="dot {esc(tone)}"></i><span class="lb">{esc(c["label"])}</span><span class="sp">&middot;</span>'
            f'<span class="tx">{chars}</span></div></div>')


def status_type(tl, c, cues):
    """The chip lands with its label; the text types on right after (or on its own word: "text_at")."""
    f = c.get("text_f", c["f0"] + 7)
    for i, ch in enumerate(c["text"]):
        fi = f + int(i * FPS / 34)
        tl.set(f"#{c['id']}t{i}", fi / FPS, {"visibility": "visible"})


def prompt_html(pl, c, y, tl, cues):
    pc = pl.cfg["prompt"]
    text = c["text"]
    f0, f1 = c["f0"], c["f1"]
    send = c.get("send_f", min(f1 - 1, f0 + 6 + int(len(text) * FPS / pc["cps"])))
    done = c.get("done_f")
    span = max(4, send - f0 - 8)
    cps = max(pc["cps"], len(text) * FPS / span)
    pid, did = c["id"], c["id"] + "d"
    chars = "".join(f'<s id="{pid}c{i}">{esc(ch) if ch != " " else "&nbsp;"}</s>' for i, ch in enumerate(text))
    t_end = done if done else f1
    label = c.get("label", pc.get("label", "")) or ""
    out = [f'<div class="row" style="top:{y}px"><div class="el prompt{"" if label else " nolabel"}" id="{pid}" {kit.box("card", f0 / FPS, t_end / FPS)}>'
           f'<div class="lb">{esc(label)}<span class="st el" id="{pid}s">SENT</span>'
           f'<span class="dots el" id="{pid}w"><i></i><i></i><i></i></span></div>'
           f'<div class="tx">{chars}<span class="caret" id="{pid}k"></span></div>'
           f'<div class="go" id="{pid}g">{ARROW}</div></div></div>']
    pop_in(tl, f"#{pid}", f0)
    cues.append((f0, "pop_lo", -3))
    for i in range(len(text)):
        fi = f0 + 5 + int(i * FPS / cps)
        tl.set(f"#{pid}c{i}", fi / FPS, {"display": "inline"})
        if i % 3 == 0 and text[i] != " ":
            cues.append((fi, "key", -11))
    tl.set(f"#{pid}k", send / FPS, {"opacity": 0})
    tl.fromto(f"#{pid}g", send / FPS, {"scale": 0.8}, {"scale": 1}, 0.28, "back.out(2)")
    tl.set(f"#{pid}s", send / FPS, {"opacity": 1, "visibility": "visible"})
    tl.set(f"#{pid}w", send / FPS, {"opacity": 1, "visibility": "visible"})
    for k in range(3):
        tl.raw(f'tl.to("#{pid}w i:nth-child({k + 1})",{{opacity:1,duration:0.22,repeat:{max(1, int((t_end - send) / 9))},yoyo:true,ease:"sine.inOut"}},{kit.snap(send / FPS + 0.12 * k)});')
    cues.append((send, "click", -2))
    tl.event(send / FPS, "tick", f"{pid} sent", region=[80, y, 920, 108], sel=f"#{pid}s", show=True)
    if done:
        # the prompt folds into its result chip
        tl.to(f"#{pid}", (done - 4) / FPS, {"scaleX": 0.78, "opacity": 0.2, "filter": "blur(8px)"}, 4 / FPS, "power3.in")
        hide(tl, f"#{pid}", done)
        out.append(f'<div class="row" style="top:{y + 12}px"><div class="el chip" id="{did}" {kit.box("card", done / FPS, f1 / FPS)}>'
                   f'<span class="ok">{CHECK.format(s=24)}</span><span class="lb">DONE</span><span class="sp">&middot;</span>'
                   f'<span class="tx">{esc(c.get("done_text", "done"))}</span></div></div>')
        pop_in(tl, f"#{did}", done, {"opacity": 0.6, "scaleX": 1.3, "scale": 0.86, "filter": "blur(10px)"}, 0.42)
        tl.fromto(f"#{did} .ok", done / FPS, {"scale": 0.3, "rotation": -90}, {"scale": 1, "rotation": 0}, 0.4, "back.out(2.2)")
        cues.append((done, "chime", -7))
        tl.event(done / FPS, "enter", f"{pid} done", region=[190, y + 12, 700, 84], sel=f"#{did}", show=True)
    tl.event(f0 / FPS, "enter", f"{pid} prompt", region=[80, y, 920, 108 + FLY_TRAVEL], sel=f"#{pid}", show=True)
    return "".join(out)


def panel_html(c, y, tl, cues):
    pid, f0 = c["id"], c["f0"]
    rows = []
    for i, r in enumerate(c.get("rows", [])):
        rid = f"{pid}r{i}"
        rows.append(f'<div class="pr" id="{rid}">{"<span class=hl id=" + rid + "h></span>" if r.get("hl") else ""}'
                    f'<span class="ck"><span class="f" id="{rid}f">{CHECK.format(s=24)}</span></span>'
                    f'<span class="pt">{esc(r["text"])}</span></div>')
    count = f'{len(c.get("rows", []))} ITEM{"S" if len(c.get("rows", [])) != 1 else ""}'
    html = (f'<div class="row" style="top:{y}px"><div class="el panel" id="{pid}" {kit.box("card", f0 / FPS, c["f1"] / FPS)}>'
            f'<div class="ph"><span>{esc(c.get("title", ""))}</span><i>{esc(c.get("meta", count))}</i></div>{"".join(rows)}</div></div>')
    pop_in(tl, f"#{pid}", f0)
    cues.append((f0, "pop", -1))
    h = H_EST["panel_head"] + H_EST["panel_row"] * len(c.get("rows", []))
    tl.event(f0 / FPS, "enter", f"{pid} panel", region=[100, y, 880, h + FLY_TRAVEL], sel=f"#{pid}", show=True)
    for i, r in enumerate(c.get("rows", [])):
        rid, fr = f"{pid}r{i}", r["f"]
        late = fr > f0 + 2 and r.get("show", "start") == "at"
        if late:
            tl.set(f"#{rid}", 0, {"opacity": 0})
            tl.fromto(f"#{rid}", fr / FPS, {"opacity": 0.5, "x": -14}, {"opacity": 1, "x": 0}, 0.26, "power3.out")
        ft = max(fr, f0 + 3)
        tl.fromto(f"#{rid}f", ft / FPS, {"opacity": 0.4, "scale": 0.6}, {"opacity": 1, "scale": 1}, 0.24, "back.out(2)")
        if r.get("hl"):
            tl.fromto(f"#{rid}h", ft / FPS, {"opacity": 0.4, "scaleX": 0.05, "transformOrigin": "0% 50%"},
                      {"opacity": 1, "scaleX": 1}, 0.38, "expo.out")
        if ft > f0 + 3:
            cues.append((ft, "pop_hi", -6))
            ry = y + H_EST["panel_head"] + H_EST["panel_row"] * i
            tl.event(ft / FPS, "tick", f"{rid} tick", region=[136, ry, 60, 78])
    return html


def cover_html(pl, c, tl, cues, tok):
    cid, f0, f1 = c["id"], c["f0"], c["f1"]
    rnd = random.Random(c.get("seed", 7))
    bars = "".join(f'<i style="width:{rnd.choice((1, 1, 2, 2, 3, 4))}px;margin-right:{rnd.choice((1, 2, 2, 3))}px"></i>' for _ in range(44))
    kk = [c.get("issue", "NO. 01"), c.get("tag", ""), c.get("date", "")]
    kk_html = "".join(f'<span {kit.box("text", f0 / FPS, f1 / FPS)}>{esc(x)}</span>' for x in kk if x)
    html = (f'<div class="el cover" id="{cid}"><div class="bd" {kit.box("frame", f0 / FPS, f1 / FPS, readable=False)}></div><div class="bd2"></div>'
            f'<div class="kk">{kk_html}</div>'
            f'<div class="bc" {kit.box("card", f0 / FPS, f1 / FPS)}><div class="bars">{bars}</div>'
            f'<div class="nm">{esc(c.get("code", "0 2601 2026"))}</div></div></div>'
            f'<div class="flash" id="{cid}x"></div>')
    tl.set(f"#{cid}", f0 / FPS, {"visibility": "visible"})
    tl.fromto(f"#{cid}", f0 / FPS, {"opacity": 0.7, "scale": 1.025}, {"opacity": 1, "scale": 1}, 0.3, "power3.out")
    tl.set(f"#{cid}x", f0 / FPS, {"visibility": "visible"})
    tl.fromto(f"#{cid}x", f0 / FPS, {"opacity": 0.22}, {"opacity": 0}, 0.14, "power2.out")
    tl.set(f"#{cid}x", f0 / FPS + 0.24, {"visibility": "hidden"})
    cues.append((f0, "shutter", 0))
    tl.event(f0 / FPS, "enter", f"{cid} cover", region=[44, 232, 992, 60], sel=f"#{cid}", show=True)
    return html


def countdown_html(c, y, tl, cues, pl_days=84):
    cid, f0, f1 = c["id"], c["f0"], c["f1"]
    days = int(c.get("days", pl_days))
    rnd = random.Random(3)

    def v(vals, vid):
        units = ("DAYS", "HRS", "MIN", "SEC")
        inner = '<span class="c">:</span>'.join(f'<span class="u"><b>{x:02d}</b><i>{u}</i></span>' for x, u in zip(vals, units))
        return f'<div class="v" id="{vid}">{inner}</div>'

    scr = [[rnd.randint(10, 99), rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59)] for _ in range(5)]
    seq = scr + [[days, 0, 0, 0]]
    ticks = []
    t = 1
    first = int(c.get("first_tick_s", 0.6) * FPS)
    while f0 + first + (t - 1) * FPS < f1:
        ticks.append(t)
        t += 1
    vs = "".join(v(x, f"{cid}v{i}") for i, x in enumerate(seq))
    vs += "".join(v([days - 1, 23, 59, 60 - k], f"{cid}t{k}") for k in ticks)
    html = (f'<div class="row" style="top:{y}px"><div class="el cd" id="{cid}" {kit.box("card", f0 / FPS, f1 / FPS)}>'
            f'<div class="cl"><span>{esc(c.get("label", "DEADLINE SET"))}</span><i><b></b>LIVE</i></div><div class="dg">{vs}</div></div></div>')
    pop_in(tl, f"#{cid}", f0)
    cues.append((f0, "pop_lo", -2))
    for i in range(len(seq)):
        fi = f0 + i
        tl.set(f"#{cid}v{i}", fi / FPS, {"visibility": "visible"})
        if i + 1 < len(seq):
            tl.set(f"#{cid}v{i}", (fi + 1) / FPS, {"visibility": "hidden"})
    last = f"#{cid}v{len(seq) - 1}"
    for k in ticks:
        fk = f0 + first + (k - 1) * FPS
        tl.set(last, fk / FPS, {"visibility": "hidden"})
        tl.set(f"#{cid}t{k}", fk / FPS, {"visibility": "visible"})
        last = f"#{cid}t{k}"
        cues.append((fk, "tick", -6))
    tl.event(f0 / FPS, "enter", f"{cid} countdown", region=[180, y, 720, 186 + FLY_TRAVEL], sel=f"#{cid}", show=True)
    return html


# ------------------------------------------------------------------ subtitles
def subtitles(pl, tl, caps):
    import captions as _caps  # split template (phrase chunking, no orphans)
    sc = pl.cfg["subtitle"]
    slices = [{"t0": s["t0"], "t1": s["t1"], "seg": s["id"], "layout": s["scene"]} for s in pl.segs]
    chs = _caps.chunks(pl.proj.words, slices, sc["max_words"], sc["max_chars"], mode="pill")
    ws = pl.proj.words_raw
    out, wi = [], 0
    for i, c in enumerate(chs):
        toks = c["text"].split()
        while wi < len(ws) and ws[wi]["text"] != toks[0]:
            wi += 1
        idx = list(range(wi, wi + len(toks)))
        wi += len(toks)
        f0, f1 = kit.frame_of(c["t0"]), kit.frame_of(c["t1"])
        if f1 <= f0:
            f1 = f0 + 1
        s = pl.seg_of_frame(f0)
        cid = f"s{i}"
        spans = []
        for j, k in enumerate(idx):
            spans.append(f'<b id="{cid}w{j}">{esc(ws[k]["text"])}</b>')
            fw = max(f0, kit.frame_of(float(ws[k]["start"])))
            tl.set(f"#{cid}w{j}", fw / FPS, {"color": pl.tok["cream"]})
            if j + 1 < len(idx):
                fn = max(f0, kit.frame_of(float(ws[idx[j + 1]]["start"])))
                tl.set(f"#{cid}w{j}", fn / FPS, {"color": theme.rgba(pl.tok["cream"], 0.78)})
        top, compact = pl.sub_top_for(f0, f1)
        out.append(f'<div class="sub{" compact" if compact else ""}" id="{cid}" style="top:{top}px"><span class="p" data-fit="960,30" '
                   f'{kit.box("caption", f0 / FPS, f1 / FPS)}>{" ".join(spans)}</span></div>')
        tl.set(f"#{cid}", f0 / FPS, {"opacity": 1, "visibility": "visible"})
        tl.set(f"#{cid}", f1 / FPS, {"opacity": 0, "visibility": "hidden"})
        clamped = f0 != kit.frame_of(float(ws[idx[0]]["start"]))
        solo = len(idx) == 1 and sum(1 for w in ws if s["t0"] - 0.02 <= float(w["start"]) < s["t1"]) == 1
        caps.append({"text": c["text"], "f0": f0, "f1": f1, "words": idx, "clamped": clamped, "seg": s["id"],
                     "solo_ok": solo})     # a one-word cut can only caption that word
    return "\n".join(out)


# ------------------------------------------------------------------ bake cache
def bake_key(pl):
    h = hashlib.sha1()
    for f in ("bake.py", "layers.py", "plan.py", "etheme.py"):
        h.update(open(os.path.join(HERE, f), "rb").read())
    summ = pl.summary()
    summ["takeovers"] = [{"seg": t["seg"], "page": t["page"]} for t in summ.get("takeovers", [])]
    h.update(json.dumps(summ, sort_keys=True, default=str).encode())
    # the takeover page and tracker live in the HTML layer: tuning them never re-bakes (the page colour is in the summary)
    h.update(json.dumps({k: v for k, v in pl.cfg.items() if k not in ("takeover", "tracker")}, sort_keys=True,
                        default=str).encode())
    raw = pl.proj.p("work", "matte", "raw")
    h.update(str(len(os.listdir(raw)) if os.path.isdir(raw) else 0).encode() + __import__("bake").matte_key(pl).encode())
    return h.hexdigest()[:16]


def ensure_base(pl, log):
    import bake
    key = bake_key(pl)
    kf = pl.proj.p("work", "bake.key")
    base = pl.proj.p("assets", "base.mp4")
    if os.path.exists(base) and os.path.exists(kf) and open(kf).read().strip() == key:
        log("bake: cached")
        return
    bc = pl.cfg.get("bake") or {}
    n = int(bc.get("workers", 1))
    if bc.get("cache"):                        # one cached chunk per cut (bake_cache.py): re-plans re-bake only changes
        __import__("bake_cache").bake_cached(pl.dir, log=log, workers=max(1, n))
    else:
        __import__("bake_par").bake_parallel(pl.dir, log=log, workers=n) if n > 1 else bake.bake(pl.dir, log=log)
    with open(kf, "w") as f:
        f.write(key)


def screen_facetrack(pl):
    """Face boxes in SCREEN pixels (set punch-in applied) every 3rd frame, in the stylekit qa format."""
    boxes = {}
    for f in range(0, pl.frames, 3):
        b = pl.face_box(f)
        if b:
            boxes[str(f)] = [round(b[0]), round(b[1]), round(b[2] - b[0]), round(b[3] - b[1])]
    kit.jsave(pl.proj.p("work", "facetrack_screen.json"), {"step": 3, "fps": FPS, "frames": pl.frames, "boxes": boxes})


# ------------------------------------------------------------------ compose
def compose(project_dir, log=print, bake_layer=True):
    pl = _plan.Plan(project_dir)
    tok = theme.tokens(pl.proj.brand, pl.cfg)
    pl.tok = tok
    if bake_layer:
        ensure_base(pl, log)
    screen_facetrack(pl)
    tl, cues = kit.TL(), []
    band, gap = pl.cfg["band"]["top"], pl.cfg["band"]["gap"]

    # scene switches + headline entrances (baked) as QA events and SFX cues
    for a, b in zip(pl.segs, pl.segs[1:]):
        tl.event(b["t0"], "cut", f"cut {a['id']}>{b['id']} ({a['scene']}>{b['scene']})", region=[0, 0, 1080, 1920])
    for h in pl.headlines:
        if h["static"]:
            continue
        r = layers.render_headline(pl, h, tok, layers.top_reserved(pl, h))
        ln = r["lines"][-1]
        tl.event(h["f0"] / FPS, "enter", f"headline {h['text']}", region=[ln["x0"], ln["y0"], ln["x1"] - ln["x0"], ln["y1"] - ln["y0"]])
        cues.append((h["f0"], "thump", -5))

    # takeover pages + live cut-outs ride the camera with the plate (kit wraps the <!--mvcam--> block into #mvCam)
    tk_html, tk_css, tk_events, tk_tops = _tko.build(pl, tok, tl, cues)
    tk_html += kitcards.heroes_html(pl, tl, cues, tok)      # heroes ride the camera with the speaker (and its matte)
    for f, kind, label, region, sel in tk_events:
        tl.event(f / FPS, kind, label, region=region, frame=f, sel=sel, show=True if sel else None)
    # camera headroom: cards sit in the top band and subtitles under the chin (with margin), so punches and
    # reframes may go to 9 % here (the stylekit default caps full-frame styles at 4.5 %, which flattens punches)
    over = {s["id"]: {"kmax": float(pl.cfg.get("camera_kmax", 1.09))} for s in pl.segs}
    for t in pl.takeovers:            # a whip into the page (then the circle opens), the engine picks the move out
        over[t["seg"]]["transition"] = "whip"
        over[t["seg"]]["kmax"] = float(pl.cfg.get("takeover", {}).get("camera_kmax", 1.03))   # the page moves itself
    kit._CUR["overrides"] = over
    body = [f'<video id="base" src="assets/base.mp4" playsinline data-start="0" data-duration="{kit.duration_str(pl.frames)}" '
            f'data-track-index="0" data-has-audio="true"></video>' + (f"<!--mvcam-->{tk_html}<!--/mvcam-->" if tk_html else ""),
            '<div class="layer" id="cards">']
    for s in pl.segs:
        y = tk_tops.get(s["id"], band)
        for c in [c for c in pl.cards if c["seg"] == s["id"]]:
            k = c["kind"]
            if k in kitcards.KINDS:          # plan-compiler cards (heroes go into the camera block above)
                y = kitcards.add(body, pl, s, c, y, tl, tok) if k != "hero" else y
                continue
            if k == "status":
                body.append(status_html(c, y, tok))
                pop_in(tl, f"#{c['id']}", c["f0"])
                status_type(tl, c, cues)
                cues.append((c["f0"], "pop", 0))
                tl.event(c["f0"] / FPS, "enter", f"{c['id']} status", region=[190, y, 700, 84 + FLY_TRAVEL], sel=f"#{c['id']}", show=True)
                y += H_EST["status"] + gap
            elif k == "prompt":
                body.append(prompt_html(pl, c, y, tl, cues))
                y += H_EST["prompt"] + gap
            elif k == "panel":
                body.append(panel_html(c, y, tl, cues))
                y += H_EST["panel_head"] + H_EST["panel_row"] * len(c.get("rows", [])) + gap
            elif k == "cover":
                body.append(cover_html(pl, c, tl, cues, tok))
            elif k == "countdown":
                body.append(countdown_html(c, y, tl, cues, pl.cfg.get("countdown", {}).get("days", 84)))
                y += H_EST["countdown"] + gap
            else:
                raise SystemExit(f"unknown card kind '{k}' in {s['id']} (status, prompt, panel, cover, countdown)")
            hide(tl, f"#{c['id']}", c["f1"])
            if k == "prompt" and c.get("done_f"):
                hide(tl, f"#{c['id']}d", c["f1"])
            if s["scene"] == "room" and y > s["head_top"] - 24:
                pl.warn(f"cards in {s['id']} reach y {y}, below the head top {s['head_top']:.0f}; move one to another cut")
    body.append("</div>")
    caps = []
    body.append(subtitles(pl, tl, caps))
    for c in cues:
        tl.cue(c[0] / FPS, c[1], c[2], frame=c[0])
    html = kit.build_html(title=pl.proj.pj.get("title", "Editorial UI"), css=css(tok, pl.cfg) + tk_css,
                          fontface=theme.fontface(tok, pl.dir, pl.warn), fonts_load=theme.fonts_load(tok),
                          total=kit.duration_str(pl.frames), body="\n".join(body),
                          tween_js="\n".join("  " + j for j in tl.js), gsap_src=kit.ensure_gsap(pl.dir))
    with open(pl.proj.p("index.html"), "w") as fh:
        fh.write(html)
    kit.write_hf_config(pl.dir)
    ed = pl.cfg
    meta = {"template": "editorial-ui", "frames": pl.frames, "base_video": "assets/base.mp4", "voice_src": "assets/aroll.mp4",
            "facetrack": "work/facetrack_screen.json", "events": tl.events,
            "cues": sorted(tl.cues, key=lambda c: c["frame"]) if ed["sfx"].get("enabled", True) else [],
            "captions": {"mode": "phrase"}, "caption_list": caps,
            "loop": ed.get("loop", {"t0": 0.0}), "poster": ed.get("poster", {"t": 3.6}),
            "plan": pl.summary(), "warnings": pl.warnings}
    kit.jsave(pl.proj.p("work", "meta.json"), meta)
    log(f"compose: {pl.frames} frames, {len(pl.headlines)} headlines, {len(pl.cards)} cards, {len(caps)} subtitles, "
        f"{len(tl.events)} events, {len(meta['cues'])} sfx cues, {len(pl.warnings)} warnings")
    return meta


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    compose(sys.argv[1], bake_layer="--no-bake" not in sys.argv)
