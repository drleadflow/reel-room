#!/usr/bin/env python3
"""Desk Demo template: full-frame talking head that cuts to "phone filmed at the monitor" inserts (a mock screen built
in HTML, shown on a monitor in perspective with handheld micro-shake, screen glare and a blurred room around it),
small sentence captions, a white native label title on the hook, dry sound with one soft click per on-screen action.

  compose.py <project>     index.html + work/meta.json   (run through stylekit/build.py)

project.json "style_cfg":
  label     {"text": "...", "until": "seg:<id>"}           hook label title
  shots     [{"from": frame|"seg:id"|"@word", "to": ..., "screen": "list|panel|calendar", "cam": {...}, "scroll": [...]}]
  actions   [{"at": "@word", "kind": "click|highlight|open|event", ...}]   cursor moves + clicks (each click = one sfx)
  portal    {"title", "patient", "rows": [[test, result, unit, range, flag]], "highlight": "Fasting insulin", "tag": "Over 7"}
  tail      extra frames after the voice (the last insert holds, silence)
Mock data must be patient-agnostic and labelled "Sample".
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import kit  # noqa: E402
import deskmotion as dm  # noqa: E402
from kit import FPS, esc, frame_of  # noqa: E402

SW, SH = 1200, 750          # monitor screen, CSS px
ROW_H = 76


def css(proj):
    c, f = proj.colors, proj.fonts
    ink = c["ink"]
    return f"""
:root{{--ink:{ink};--acc:{c['accent']};--gold:{c['highlight']};--fd:{kit.fam(f['display'])};--fb:{kit.fam(f['body'])}}}
html,body{{margin:0;padding:0;background:#000}}
*{{box-sizing:border-box}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;background:#000;font-family:var(--fb)}}
#aroll{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover;z-index:1}}
.label{{position:absolute;left:0;width:1080px;z-index:20;display:flex;flex-direction:column;align-items:center;gap:0}}
.label span{{background:#fff;color:#111;font:700 54px/1.18 var(--fb);letter-spacing:-.012em;padding:6px 26px 8px;border-radius:18px;white-space:nowrap;
  box-shadow:0 6px 24px rgba(0,0,0,.18)}}
.label span+span{{margin-top:-10px}}
.cap{{position:absolute;left:0;width:1080px;z-index:30;display:flex;justify-content:center;opacity:0;visibility:hidden}}
.cap span{{font:700 50px/1.1 var(--fb);color:#fff;letter-spacing:-.01em;white-space:nowrap;padding:9px 20px 11px;border-radius:14px;
  background:rgba(16,16,18,.58);text-shadow:0 1px 2px rgba(0,0,0,.35)}}
/* ---------------- phone-at-the-monitor insert */
.ins{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:10;overflow:hidden;opacity:0;visibility:hidden;background:#141210}}
.room{{position:absolute;inset:-60px;background-size:cover;background-position:center;filter:blur(26px) brightness(.5) saturate(.85)}}
.desk{{position:absolute;left:-200px;right:-200px;top:1360px;height:900px;
  background:linear-gradient(180deg,#2a2420 0%,#1c1815 40%,#120f0d 100%);filter:blur(1.5px)}}
.kb{{position:absolute;left:150px;top:1600px;width:860px;height:300px;border-radius:26px;background:#232224;filter:blur(10px) brightness(.8);
  box-shadow:inset 0 0 0 3px #3a393b;transform:perspective(900px) rotateX(48deg)}}
.kb i{{position:absolute;left:40px;right:40px;height:34px;border-radius:8px;background:repeating-linear-gradient(90deg,#4a494c 0 52px,#2e2d2f 52px 62px)}}
.cam{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 900px}}
.mon{{position:absolute;width:{SW + 44}px;height:{SH + 70}px;border-radius:22px;background:#0b0b0d;
  box-shadow:0 40px 120px rgba(0,0,0,.6),inset 0 0 0 2px #1b1b1f,inset 0 2px 0 #2a2a30}}
.scr{{position:absolute;left:22px;top:22px;width:{SW}px;height:{SH}px;overflow:hidden;border-radius:4px;background:#F4F6F9;
  filter:contrast(.93) brightness(1.03) saturate(.94) blur(.35px)}}
.glare{{position:absolute;left:22px;top:22px;width:{SW}px;height:{SH}px;pointer-events:none;border-radius:4px;
  background:linear-gradient(112deg,rgba(255,255,255,0) 28%,rgba(255,255,255,.10) 41%,rgba(255,255,255,.02) 50%,rgba(255,255,255,0) 60%),
  radial-gradient(ellipse at 70% 0%,rgba(180,205,255,.10),rgba(0,0,0,0) 60%),
  radial-gradient(ellipse at 50% 50%,rgba(0,0,0,0) 55%,rgba(0,0,0,.16) 100%)}}
.vig{{position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse 80% 60% at 50% 45%,rgba(0,0,0,0) 55%,rgba(0,0,0,.42) 100%)}}
/* portal UI (generic, no brand) */
.pt{{position:absolute;inset:0;font-family:var(--fb);color:#1d2733;word-spacing:.05em}}
.pt .top{{height:76px;background:#22364F;display:flex;align-items:center;gap:16px;padding:0 30px;color:#fff;font:700 28px/1 var(--fb)}}
.pt .top .lg{{width:40px;height:40px;border-radius:12px;background:#4E86C4;display:flex;align-items:center;justify-content:center}}
.pt .top .smp{{margin-left:auto;font:800 18px/1 var(--fb);letter-spacing:.18em;background:#F2C14E;color:#22364F;padding:9px 14px;border-radius:8px}}
.pt .side{{position:absolute;left:0;top:76px;bottom:0;width:200px;background:#fff;border-right:1.5px solid #E3E8EF;padding:26px 0}}
.pt .side div{{padding:16px 30px;font:600 22px/1 var(--fb);color:#5a6878}}
.pt .side div.on{{color:#22364F;background:#EAF1FA;border-left:5px solid #4E86C4}}
.pt .main{{position:absolute;left:200px;right:0;top:76px;bottom:0;overflow:hidden}}
.pt .pg{{position:absolute;left:0;right:0;top:0;padding:30px 44px}}
.pt h1{{margin:0;font:800 42px/1.1 var(--fd);letter-spacing:-.02em;color:#16202b}}
.pt .meta{{margin-top:10px;font:500 22px/1.3 var(--fb);color:#6b7887}}
.pt .meta b{{color:#22364F}}
.pt .list{{margin-top:28px;display:flex;flex-direction:column;gap:16px}}
.pt .it{{background:#fff;border:1.5px solid #E1E7EE;border-radius:16px;padding:24px 28px;display:flex;align-items:center;gap:22px}}
.pt .it .ic{{width:56px;height:56px;border-radius:14px;background:#EAF1FA;display:flex;align-items:center;justify-content:center}}
.pt .it .nm{{font:700 30px/1.1 var(--fb);color:#16202b}}
.pt .it .sb{{font:500 21px/1.2 var(--fb);color:#6b7887;margin-top:6px}}
.pt .it .st{{margin-left:auto;font:700 19px/1 var(--fb);color:#2F7D57;background:#E5F4EC;padding:9px 14px;border-radius:999px}}
.pt .it.hov{{border-color:#4E86C4;box-shadow:0 0 0 4px rgba(78,134,196,.18)}}
.pt table{{margin-top:22px;width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1.5px solid #E1E7EE;border-radius:16px;overflow:hidden}}
.pt th{{text-align:left;font:800 17px/1 var(--fb);letter-spacing:.14em;color:#7a8796;padding:20px 26px;background:#F7F9FC;border-bottom:1.5px solid #E1E7EE}}
.pt td{{height:{ROW_H}px;padding:0 26px;font:600 27px/1 var(--fb);color:#1d2733;border-bottom:1.5px solid #EEF2F6;white-space:nowrap;position:relative}}
.pt td.r{{font-weight:800}}
.pt td.u{{color:#7a8796;font-weight:500;font-size:22px}}
.pt tr.hl td{{transition:none}}
.pt .hlbg{{position:absolute;left:0;width:10px;height:{ROW_H}px;background:var(--gold);opacity:0;mix-blend-mode:multiply}}
.pt .tag{{position:absolute;padding:10px 16px;border-radius:999px;background:var(--acc);color:#fff;font:800 20px/1 var(--fb);letter-spacing:.08em;
  text-transform:uppercase;opacity:0;white-space:nowrap}}
.cur{{position:absolute;left:0;top:0;width:34px;height:50px;z-index:5;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}}
.rip{{position:absolute;width:60px;height:60px;margin:-30px 0 0 -30px;border-radius:50%;border:4px solid rgba(78,134,196,.85);opacity:0;z-index:4}}
.rip.r2{{border-width:0;background:rgba(78,134,196,.28)}}
.pt .it{{position:relative}}
.spot{{position:absolute;border-radius:14px;box-shadow:0 0 0 3000px rgba(10,16,26,.46);opacity:0;z-index:3;pointer-events:none}}
.pt .it .spot{{inset:-4px;border-radius:18px}}
.cal .d .spot{{inset:0;border-radius:4px}}
/* calendar app */
.cal{{position:absolute;inset:0;background:#fff;font-family:var(--fb);color:#1d2733}}
.cal .bar{{height:84px;display:flex;align-items:center;padding:0 36px;gap:18px;border-bottom:1.5px solid #E6E9EE;font:800 34px/1 var(--fd)}}
.cal .bar .dots{{display:flex;gap:10px}}
.cal .bar .dots i{{width:16px;height:16px;border-radius:50%;background:#E8504A}}
.cal .bar .dots i+i{{background:#F2B33D}}
.cal .bar .dots i+i+i{{background:#41B65B}}
.cal .wd{{display:grid;grid-template-columns:repeat(7,1fr);padding:0 20px;font:700 20px/1 var(--fb);letter-spacing:.14em;color:#8a95a3}}
.cal .wd div{{padding:18px 14px}}
.cal .grid{{display:grid;grid-template-columns:repeat(7,1fr);grid-auto-rows:120px;padding:0 20px}}
.cal .d{{border-top:1.5px solid #EDF0F4;border-left:1.5px solid #EDF0F4;padding:12px 14px;font:600 26px/1 var(--fb);color:#3a4654;position:relative}}
.cal .d.mute{{color:#c3cad3}}
.cal .d.today span{{background:#E8504A;color:#fff;border-radius:999px;padding:6px 10px}}
.cal .ev{{position:absolute;left:8px;right:8px;bottom:14px;height:48px;border-radius:10px;background:var(--acc);color:#fff;
  font:800 28px/52px var(--fb);padding:0 14px;height:52px;white-space:nowrap;overflow:hidden;opacity:0;box-shadow:0 6px 16px rgba(0,0,0,.18)}}
.cal .wk{{position:absolute;left:8px;right:8px;bottom:14px;height:40px;border-radius:8px;background:#EAF1FA;color:#22364F;font:700 18px/40px var(--fb);padding:0 10px;white-space:nowrap;overflow:hidden}}
""" + (dm.PHONE_CSS + dm.NOTES_CSS if proj.motion is not None else "")


CURSOR = ('<svg class="cur" id="{id}" viewBox="0 0 34 50"><path d="M3 2 L3 40 L12 31 L18 46 L25 43 L19 28 L31 28 Z" '
          'fill="#fff" stroke="#111" stroke-width="2.4" stroke-linejoin="round"/></svg>')
ICON_DOC = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#4E86C4" stroke-width="2" stroke-linecap="round">'
            '<path d="M7 3h7l4 4v14H7z"/><path d="M10 12h5M10 16h5"/></svg>')
ICON_DROP = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4"><path d="M12 3.5c3 4.2 6 7.2 6 10.6a6 6 0 0 1-12 0c0-3.4 3-6.4 6-10.6z"/></svg>')


def portal_html(cfg, sid):
    p = cfg["portal"]
    side = "".join(f'<div class="{"on" if i == 1 else ""}">{esc(x)}</div>' for i, x in enumerate(["Overview", "Lab results", "Visits", "Messages"]))
    items = "".join(f'<div class="it{" " if i else " first"}" id="{sid}it{i}"><div class="ic">{ICON_DOC}</div><div><div class="nm">{esc(n)}</div>'
                    f'<div class="sb">{esc(sub)}</div></div><div class="st">{esc(st)}</div><div class="spot" id="{sid}spi{i}"></div></div>'
                    for i, (n, sub, st) in enumerate(p["reports"]))
    rows = []
    for r in p["rows"]:
        hl = r[0] == p.get("highlight")
        rows.append(f'<tr{" class=hl" if hl else ""}><td>{esc(r[0])}</td><td class="r">{esc(r[1])} <span class="u">{esc(r[2])}</span></td>'
                    f'<td class="u">{esc(r[3])}</td></tr>')
    return f"""<div class="pt">
<div class="top"><div class="lg">{ICON_DROP}</div>{esc(p["app"])}<span class="smp">SAMPLE</span></div>
<div class="side">{side}</div>
<div class="main">
 <div class="pg" id="{sid}list"><h1>Lab results</h1><div class="meta"><b>{esc(p["patient"])}</b> &middot; {esc(p["note"])}</div>
  <div class="list">{items}</div></div>
 <div class="pg" id="{sid}panel" style="opacity:0"><div id="{sid}scroll" style="position:relative">
  <h1>{esc(p["panel_title"])}</h1><div class="meta"><b>{esc(p["patient"])}</b> &middot; {esc(p["note"])}</div>
  <table><thead><tr><th style="width:44%">TEST</th><th style="width:30%">RESULT</th><th>REFERENCE</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
  <div class="hlbg" id="{sid}hl"></div><div class="spot" id="{sid}spot"></div><div class="tag" id="{sid}tag">{esc(p.get("tag", ""))}</div>
 </div></div>
</div></div>"""


def calendar_html(cfg, sid):
    c = cfg["calendar"]
    days = []
    start_blank = c.get("first_weekday", 0)
    n_days = c.get("days", 31)
    cells = start_blank + n_days
    cells += (7 - cells % 7) % 7
    for k in range(cells):
        d = k - start_blank + 1
        if d < 1 or d > n_days:
            days.append('<div class="d mute"></div>')
            continue
        inner = f"<span>{d}</span>"
        if d == c.get("today"):
            days.append(f'<div class="d today">{inner}</div>')
            continue
        if d == c["pick"]:
            inner += f'<div class="spot" id="{sid}spd"></div><div class="ev" id="{sid}ev">{esc(c["event"])}</div>'
        for wday, txt in c.get("marks", {}).items():
            if int(wday) == d:
                inner += f'<div class="wk">{esc(txt)}</div>'
        days.append(f'<div class="d" id="{sid}d{d}">{inner}</div>')
    wd = "".join(f"<div>{x}</div>" for x in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"])
    return (f'<div class="cal"><div class="bar"><span class="dots"><i></i><i></i><i></i></span>{esc(c["month"])}'
            f'<span style="margin-left:auto;font:800 18px/1 var(--fb);letter-spacing:.18em;color:#8a95a3">SAMPLE</span></div>'
            f'<div class="wd">{wd}</div><div class="grid">{"".join(days)}</div></div>')


def shake(n, seed, amp=1.0):
    """Handheld micro-shake: smooth deterministic sum of sines (px, deg) per frame."""
    import random
    rnd = random.Random(seed)
    ph = [rnd.random() * 6.283 for _ in range(9)]
    out = []
    for i in range(n):
        t = i / FPS
        x = amp * (3.2 * math.sin(6.283 * 0.53 * t + ph[0]) + 1.5 * math.sin(6.283 * 1.7 * t + ph[1]) + 0.5 * math.sin(6.283 * 4.3 * t + ph[2]))
        y = amp * (2.8 * math.sin(6.283 * 0.47 * t + ph[3]) + 1.3 * math.sin(6.283 * 1.9 * t + ph[4]) + 0.5 * math.sin(6.283 * 3.9 * t + ph[5]))
        r = amp * (0.22 * math.sin(6.283 * 0.39 * t + ph[6]) + 0.08 * math.sin(6.283 * 1.3 * t + ph[7]))
        out.append({"x": round(x, 2), "y": round(y, 2), "rotation": round(r, 3)})
    return out


def scroll_expr(sid, y):
    """y: px, or {"hl": screen_y} = scroll so the highlighted row's top sits at screen_y inside the page."""
    if isinstance(y, dict):
        return f"-(RR_HL['{sid}'] - {float(y['hl'])})"
    return f"{-float(y)}"


INIT_JS = """  window.RR_HL = {};
  document.querySelectorAll('[id$="scroll"]').forEach(sc => {
    const tr = sc.querySelector('tr.hl'), tb = sc.querySelector('table'); if (!tr || !tb) return;
    const sid = sc.id.slice(0, -6), top = tb.offsetTop + tr.offsetTop;
    RR_HL[sid] = top;
    const hl = document.getElementById(sid + 'hl'), tag = document.getElementById(sid + 'tag');
    if (hl) { hl.style.top = top + 'px'; hl.style.left = tb.offsetLeft + 'px'; hl.style.width = tb.offsetWidth + 'px'; }
    const sp = document.getElementById(sid + 'spot');
    if (sp) { sp.style.top = top + 'px'; sp.style.left = tb.offsetLeft + 'px'; sp.style.width = tb.offsetWidth + 'px';
      sp.style.height = tr.offsetHeight + 'px'; }
    const rc = tr.querySelector('td.r');
    if (tag && rc) { tag.style.top = (top + (tr.offsetHeight - 40) / 2) + 'px'; tag.style.left = (tb.offsetLeft + 250) + 'px'; }
  });"""


def resolve(proj, spec, lo=0.0):
    if isinstance(spec, int):
        return spec
    if isinstance(spec, str) and spec.startswith("seg:"):
        return next(s["frame"] for s in proj.segments if s["id"] == spec[4:])
    return frame_of(proj.at(spec, lo))


# ---------------------------------------------------------------- captions (2-5 word sentence chunks)
WEAK_END = {"i", "a", "an", "the", "your", "my", "to", "of", "is", "was", "will", "and", "that", "when", "with", "in",
            "it", "on", "you", "i've", "i'm", "be", "for", "about", "if", "as", "are", "also", "would", "should", "could",
            "has", "have", "come", "get", "tell", "can", "do", "need", "so", "but", "or", "how", "what"}
NO_SPLIT = {("fasting", "insulin"), ("insulin", "levels"), ("insulin", "level"), ("insulin", "resistance"), ("come", "up"),
            ("health", "coach"), ("blood", "work"), ("metabolic", "health"), ("get", "shredded"), ("a", "lot")}


def chunk_words(words, max_words=6, max_chars=26, gap=0.45):
    """Phrases split at punctuation and pauses, then each phrase cut into 2-5 word chunks by a small DP that prefers
    3-4 words, never ends a chunk on a weak word (I, the, your, and...) and never leaves a single word alone."""
    import re as _re
    phrases, cur = [], []
    for i, w in enumerate(words):
        if cur and (float(w["start"]) - float(words[cur[-1]]["end"]) > gap or words[cur[-1]]["text"][-1:] in ".,?!;:"):
            phrases.append(cur)
            cur = []
        cur.append(i)
    if cur:
        phrases.append(cur)

    def bare(j):
        return _re.sub(r"[^\w']", "", words[j]["text"].lower())

    def cost(p, nxt=None):
        chars = sum(len(words[j]["text"]) + 1 for j in p) - 1
        if chars > max_chars or len(p) > max_words:
            return 1e9
        c = {1: 30, 2: 4, 3: 0, 4: 0, 5: 3, 6: 7}[len(p)]
        if bare(p[-1]) in WEAK_END and words[p[-1]]["text"][-1:] not in ".,?!":
            c += 14
        if nxt is not None and ((bare(p[-1]), bare(nxt)) in NO_SPLIT or bare(p[-1]).isdigit()):
            c += 25
        return c

    chunks = []
    for ph in phrases:
        n = len(ph)
        best = [0.0] + [1e18] * n
        back = [0] * (n + 1)
        for e in range(1, n + 1):
            for st in range(max(0, e - max_words), e):
                v = best[st] + cost(ph[st:e], ph[e] if e < n else None)
                if v < best[e]:
                    best[e], back[e] = v, st
        parts, e = [], n
        while e > 0:
            parts.append(ph[back[e]:e])
            e = back[e]
        chunks += parts[::-1]
    # a lone word (one-word phrase) joins the next chunk when it is short and close, else the previous one
    out = []
    i = 0
    while i < len(chunks):
        p = chunks[i]
        if len(p) == 1 and i + 1 < len(chunks) and len(chunks[i + 1]) < max_words and \
                float(words[chunks[i + 1][0]]["start"]) - float(words[p[0]]["end"]) < 0.6:
            chunks[i + 1] = p + chunks[i + 1]
        elif len(p) == 1 and out and len(out[-1]) < max_words:
            out[-1] = out[-1] + p
        else:
            out.append(p)
        i += 1
    return out


def captions(proj, tl, total_frames, caps, inserts=(), band_top=None):
    ws = proj.words_raw
    html = []
    chunks = chunk_words(ws)
    ft = proj.facetrack["boxes"]
    for ci, ch in enumerate(chunks):
        s = float(ws[ch[0]]["start"])
        e = float(ws[ch[-1]]["end"])
        nxt = float(ws[chunks[ci + 1][0]]["start"]) if ci + 1 < len(chunks) else None
        end = nxt if (nxt is not None and nxt - e < 0.45) else e + 0.3
        f0, f1 = frame_of(s), min(frame_of(end), total_frames)
        text = " ".join(ws[j]["text"] for j in ch)
        bottoms = [v[1] + v[3] * 1.2 for k, v in ft.items() if f0 - 3 <= int(k) <= f1 + 3]
        top = int(min(max(1300, (max(bottoms) + 40) if bottoms else 1300), 1380))
        if band_top and any(a < f1 and f0 < b for a, b in inserts):  # over a screen insert: the clear desk band
            top = band_top
        cid = f"cp{ci}"
        html.append(f'<div class="cap" id="{cid}" style="top:{top}px"><span {kit.box("caption", f0 / FPS, f1 / FPS, True)}>{esc(text)}</span></div>')
        tl.set(f"#{cid}", f0 / FPS, {"opacity": 1, "visibility": "visible"})
        tl.set(f"#{cid}", f1 / FPS, {"opacity": 0, "visibility": "hidden"})
        caps.append({"text": text, "f0": f0, "f1": f1, "words": ch})
    return "\n".join(html)



# ---------------------------------------------------------------- motion v2 (deskmotion.py)
def _aims(proj, sh, c, t0):
    """Clicked UI points of a shot in frame px with the frame offset of each click (for the handheld push)."""
    out = []
    for act in sh.get("actions", []):
        ta = proj.at(act["at"], t0 - 0.05)
        px, py = dm.to_frame(c, act["x"], act["y"])
        out.append((frame_of(ta) - frame_of(t0), px, py, act.get("push", 1.14)))
    return out


def _shot_motion(proj, tl, sh, k, sid, c, f0, f1, total, js, filt_ids):
    """Handheld camera with a push toward each click, a focus pull on the first frames, whip in / whip out."""
    n = f1 - f0
    bottom = c["_at"][1] + (SH - c["focus"][1] + 30) * c["s"]          # monitor bottom edge in frame px
    rows = dm.handheld(n, seed=k + 3, amp=sh.get("shake", 1.25), push=sh.get("push", 0.04), aims=_aims(proj, sh, c, f0 / FPS),
                       bottom=bottom)
    js.append(dm.keys(f"#{sid}cam", ["x", "y", "rotation", "scale"], [[f0 + i] + r for i, r in enumerate(rows)]))
    dm.focus_pull(tl, f"#{sid}scr", f0 / FPS)
    shots = proj.style["shots"]
    starts = {resolve(proj, o["from"]) for o in shots}
    enter = -1 if k % 2 else 1
    leave = (1 if k % 2 else -1) if f1 < total else 0
    filt_ids.append(f"ddMB{k}")
    js.append(dm.keys(f"#{sid}", ["x", "scale", "bx", "by"], dm.whip_rows(f0, f1, k, enter, leave), f"ddMB{k}"))
    if f0 in {resolve(proj, o["to"]) for o in shots if o["to"] != "end"}:
        tl.cue(f0 / FPS, "swish", -4)          # screen -> screen: a new handheld angle, its own soft swish
    _ = starts


def _spotlight(tl, sid, act, ta, t1):
    """Dim the screen around the UI the click acts on (the row, the report, the day), then hold it."""
    sel = {"open": f"#{sid}spi0", "highlight": f"#{sid}spot", "event": f"#{sid}spd"}.get(act.get("kind"))
    if not sel:
        return
    t_on = ta - 0.25 if act.get("kind") == "open" else ta + 0.05
    tl.fromto(sel, t_on, {"opacity": 0}, {"opacity": 1}, 0.3 if act.get("kind") == "open" else 0.35, "power2.out")
    if act.get("kind") == "open":
        tl.to(sel, ta + 0.1, {"opacity": 0}, 0.1, "power2.in")
    tl.event(t_on, "enter", "spotlight", region=[100, 400, 880, 600])


def _engine_cuts(proj, cfg, total, phone_win):
    """Tell the engine planner how the cutaways cut: a whip on every face <-> screen cut (the cutaway does its half of
    the whip itself), nothing on cuts hidden under a screen or owned by the phone frame."""
    ov, cuts = {}, []
    wins = [(resolve(proj, sh["from"]), total if sh["to"] == "end" else resolve(proj, sh["to"])) for sh in cfg["shots"]]
    seg_at = {s["frame"]: s["id"] for s in proj.segments}
    for a, b in wins:
        for f, sid in seg_at.items():
            if a < f < b:
                ov[sid] = {"transition": "none"}
        for f in (a, b):
            if f >= total or any(x < f < y for x, y in wins):
                continue
            if any(f in (x, y) for x, y in wins if (x, y) != (a, b)):   # screen -> screen: hidden under the cutaways
                if f in seg_at:
                    ov[seg_at[f]] = {"transition": "none"}
                continue
            if f in seg_at:
                ov[seg_at[f]] = {"transition": "whip"}
            else:
                cuts.append({"frame": f, "transition": "whip"})
    if phone_win and phone_win[1] in seg_at:
        ov[seg_at[phone_win[1]]] = {"transition": "none"}
    for sg in proj.segments:   # face segments: captions sit below the chin, the head grows from it, so allow real reframes
        if not any(x <= sg["frame"] and sg["frame"] + sg["frames"] <= y for x, y in wins):
            ov.setdefault(sg["id"], {})["kmax"] = float(cfg.get("face_kmax", 1.09))
    kit._CUR["overrides"], kit._CUR["cuts"] = ov, cuts


# ---------------------------------------------------------------- compose
def room_still(proj):
    out = proj.p("assets", "room_blur.jpg")
    if not os.path.exists(out):
        kit.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", proj.p("assets", "aroll.mp4"), "-frames:v", "1",
                 "-vf", "crop=1080:760:0:120,scale=1080:1920,gblur=sigma=18", "-q:v", "3", out])
    return "assets/room_blur.jpg"


def compose(project_dir, log=print):
    proj = kit.Project(project_dir)
    voice_frames = sum(s["frames"] for s in proj.segments)
    cfg = proj.style
    total = voice_frames + int(cfg.get("tail", 0))
    proj.frames = total
    proj.facetrack = kit.jload(proj.p("work", "facetrack.json"))
    tl = kit.TL()
    room = room_still(proj)
    mot = proj.motion is not None          # motion v2 (deskmotion.py); "motion": false = the legacy render
    js_extra, filt_ids = [], []
    body = [f'<video id="aroll" src="assets/aroll.mp4" playsinline data-start="0" data-duration="{kit.duration_str(voice_frames)}" '
            f'data-track-index="0" data-has-audio="true"></video>']
    # hook label
    lab = cfg.get("label")
    if lab:
        f1 = resolve(proj, lab["until"])
        spans = "".join(f'<span {kit.box("title", 0, f1 / FPS, True)}>{esc(l)}</span>' for l in lab["lines"])
        body.append(f'<div class="label" id="lab" style="top:{lab.get("y", 300)}px" {kit.box("card", 0, f1 / FPS, False)}>{spans}</div>')
        tl.set("#lab", f1 / FPS, {"opacity": 0, "visibility": "hidden"})
        tl.event(f1 / FPS, "cut", "label off", region=[100, lab.get("y", 300), 880, 160], sel="#lab", show=False)
    # inserts
    for k, sh in enumerate(cfg["shots"]):
        sid = f"s{k}"
        f0, f1 = resolve(proj, sh["from"]), min(resolve(proj, sh["to"]) if sh["to"] != "end" else total, total)
        t0, t1 = f0 / FPS, f1 / FPS
        screen = portal_html(cfg, sid) if sh["screen"] in ("list", "panel") else calendar_html(cfg, sid)
        c = sh["cam"]
        fx, fy = c["focus"]          # screen point (CSS px) that the phone is aimed at
        tx, ty = c.get("at", [540, 820])  # where that point lands in the frame
        band = cfg.get("screen_band")    # [top, bottom]: the whole screen sits in this strip (captions go below it)
        if band:
            c = dict(c, s=min(c["s"], (band[1] - band[0]) / SH))
            ty = band[0] + fy * c["s"]
        ox, oy = fx + 22, fy + 22
        mon_tf = (f"left:{tx - ox}px;top:{ty - oy}px;transform-origin:{ox}px {oy}px;transform:perspective(2600px) "
                  f"rotateY({c.get('ry', -10)}deg) rotateX({c.get('rx', 4)}deg) rotateZ({c.get('rz', -1.5)}deg) scale({c['s']})")
        body.append(
            f'<div class="ins" id="{sid}" {kit.box("cutaway", t0, t1, False)} style="background:#141210">'
            f'<div class="room" style="background-image:url(\'{room}\')"></div><div class="desk"></div>'
            f'<div class="kb"><i style="top:40px"></i><i style="top:88px"></i><i style="top:136px"></i><i style="top:184px"></i></div>'
            f'<div class="cam" id="{sid}cam"><div class="mon" style="{mon_tf}"><div class="scr" id="{sid}scr" {kit.box("screen", t0, t1, False)}>{screen}'
            f'<div class="rip r2" id="{sid}rip2"></div><div class="rip" id="{sid}rip"></div>{CURSOR.format(id=sid + "cur")}</div><div class="glare"></div></div></div>'
            f'<div class="vig"></div></div>')
        tl.set(f"#{sid}", t0, {"opacity": 1, "visibility": "visible"})
        tl.set(f"#{sid}", t1, {"opacity": 0, "visibility": "hidden"})
        tl.event(t0, "cut", f"cut to screen ({sh['screen']})", region=[0, 0, 1080, 1920], sel=f"#{sid}", show=True)
        if f1 < total:
            nxt_screen = any(resolve(proj, o["from"]) == f1 for o in cfg["shots"])
            tl.event(t1, "cut", "new handheld angle" if nxt_screen else "back to speaker", region=[0, 0, 1080, 1920],
                     sel=f"#{sid}", show=False)
        c["_at"] = (tx, ty)
        if mot:
            _shot_motion(proj, tl, sh, k, sid, c, f0, f1, total, js_extra, filt_ids)
        else:   # legacy (motion off): micro-shake + slow push
            sk = shake(f1 - f0, seed=k + 3, amp=sh.get("shake", 1.0))
            push = sh.get("push", 0.03)
            for i, fr in enumerate(sk):
                fr["scale"] = round(1 + push * (i / max(1, f1 - f0)), 4)
            tl.keyframes(f"#{sid}cam", t0, sk)
        # screen state at shot start
        if sh["screen"] == "panel":
            tl.set(f"#{sid}list", t0, {"opacity": 0})
            tl.set(f"#{sid}panel", t0, {"opacity": 1})
        if "scroll0" in sh:
            tl.raw(f"tl.set('#{sid}scroll',{{y:{scroll_expr(sid, sh['scroll0'])}}},{kit.snap(t0)});")
        for sc in sh.get("scroll", []):
            a = proj.at(sc["at"], t0 - 0.05)
            tl.raw(f"tl.to('#{sid}scroll',{{y:{scroll_expr(sid, sc['y'])},duration:{sc.get('dur', 1.2)},ease:'power2.inOut'}},{kit.snap(a)});")
            if mot:   # motion blur that follows the scroll speed
                filt_ids.append(f"ddSB{k}")
                js_extra.append(dm.keys(f"#{sid}scroll", ["bx", "by"], dm.scroll_blur(frame_of(a), sc.get("dur", 1.2)), f"ddSB{k}"))
                tl.event(a, "enter", "scroll", region=[150, 400, 800, 700])
        cur = sh.get("cursor", {"x": 900, "y": 500})
        tl.set(f"#{sid}cur", t0, {"x": cur["x"], "y": cur["y"]})
        for act in sh.get("actions", []):
            ta = proj.at(act["at"], t0 - 0.05)
            fa = frame_of(ta)
            mv = act.get("move", 0.55)
            tl.to(f"#{sid}cur", max(t0, ta - mv), {"x": act["x"], "y": act["y"]}, mv - 0.04, "power2.inOut")
            if act.get("click", True):
                tl.to(f"#{sid}cur", ta, {"scale": 0.86}, 0.06, "power1.out")
                tl.to(f"#{sid}cur", ta + 0.07, {"scale": 1}, 0.1, "power1.out")
                tl.set(f"#{sid}rip", ta, {"left": act["x"] + 4, "top": act["y"] + 4, "opacity": 0.9, "scale": 0.4})
                tl.to(f"#{sid}rip", ta, {"opacity": 0, "scale": 1.5 if not mot else 2.1}, 0.4 if not mot else 0.5, "power2.out")
                if mot:   # a soft filled pulse under the ring
                    tl.set(f"#{sid}rip2", ta, {"left": act["x"] + 4, "top": act["y"] + 4, "opacity": 1, "scale": 0.5})
                    tl.to(f"#{sid}rip2", ta + 0.02, {"opacity": 0, "scale": 1.4}, 0.32, "power2.out")
                tl.cue(ta, "click")
            if mot:
                _spotlight(tl, sid, act, ta, t1)
            kind = act.get("kind")
            if kind == "open":
                tl.set(f"#{sid}it0", max(t0, ta - 0.25), {"borderColor": "#4E86C4", "boxShadow": "0 0 0 4px rgba(78,134,196,.18)"})
                tl.set(f"#{sid}list", ta + 0.1, {"opacity": 0})  # a real page swaps, it does not crossfade
                tl.fromto(f"#{sid}panel", ta + 0.1, {"opacity": 0.6, "y": 10}, {"opacity": 1, "y": 0}, 0.16, "power2.out")
                tl.event(ta + 0.1, "enter", "portal opens the panel", region=[300, 500, 700, 600])
            if kind == "highlight":
                tl.fromto(f"#{sid}hl", ta, {"opacity": 0.45}, {"opacity": 0.92}, 0.2, "power1.out")
                tl.event(ta, "enter", "fasting insulin row highlights", region=[150, 600, 800, 300])
                if act.get("tag_at"):
                    tg = proj.at(act["tag_at"], ta - 0.05)
                    tl.fromto(f"#{sid}tag", tg, {"opacity": 0.4, "scale": 0.8}, {"opacity": 1, "scale": 1}, 0.28, "back.out(2)")
            if kind == "event":
                tl.fromto(f"#{sid}ev", ta, {"opacity": 0.45, "scale": 0.85}, {"opacity": 1, "scale": 1}, 0.3, "back.out(1.8)")
                tl.event(ta, "enter", "calendar deadline event", region=[140, 600, 800, 600])
        for st in sh.get("sets", []):
            tl.set(st["sel"].replace("{sid}", sid), st.get("t", t0), st["vars"])
    if mot:
        ph_html, ph_js, ph_win = dm.phone(proj, tl, cfg, resolve, frame_of, kit.box)
        body.insert(0, f'<div id="ddBack"><div class="room" style="background-image:url(\'{room}\')"></div></div>')
        body.insert(2, ph_html)
        body.append(dm.notes(proj, tl, cfg, resolve, frame_of, kit.box, esc))
        js_extra.extend(ph_js)
        _engine_cuts(proj, cfg, total, ph_win)
        body.insert(0, dm.filters_html(filt_ids))
    caps = []
    ins = [(resolve(proj, sh["from"]), total if sh["to"] == "end" else resolve(proj, sh["to"])) for sh in cfg["shots"]]
    body.append(captions(proj, tl, total, caps, ins, cfg.get("caption_band_top")))
    f = proj.fonts
    html = kit.build_html(
        title=proj.pj.get("title", "Desk demo"), css=css(proj), fontface=kit.fontface(proj),
        fonts_load=[f'700 54px "{f["body"]}"', f'800 42px "{f["display"]}"', f'600 27px "{f["body"]}"', f'900 64px "{f["display"]}"'],
        total=kit.duration_str(total), body="\n".join(body), tween_js="\n".join("  " + j for j in tl.js + js_extra),
        init_js=INIT_JS, gsap_src=kit.ensure_gsap(proj.dir))
    with open(proj.p("index.html"), "w") as fh:
        fh.write(html)
    kit.write_hf_config(proj.dir)
    meta = {"template": "desk-demo", "frames": total, "voice_src": "assets/aroll.mp4", "facetrack": "work/facetrack.json",
            "events": tl.events, "cues": tl.cues, "captions": {"mode": "phrase"}, "caption_list": caps,
            "loop": cfg.get("loop", {"t0": 12.4}), "poster": cfg.get("poster", {"t": 22.4})}
    kit.jsave(proj.p("work", "meta.json"), meta)
    log(f"compose: {total} frames, {len(tl.events)} events, {len(tl.cues)} clicks, {len(caps)} captions")
    return meta


if __name__ == "__main__":
    compose(sys.argv[1])
