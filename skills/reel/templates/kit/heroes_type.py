"""heroes_type: type heroes. title-stamp (a huge serif headline stamps in on its word, optional '≠' / italic sub-line,
with a colour-set shift), word-stamp (one huge word stamped behind the head with a cut-out, else on an in-front
slab; a small set-up line struck through) and magazine-cover (the frame becomes a cover: masthead letter-drop,
coverlines beside the head, barcode, sticker slap).

The letter stamp (letters from 1.38x, one every two frames, power4.out, origin 50% 85%, slow 1 -> 1.035 grow once
built), the word-stamp set-up line + strike and the magazine-cover beat order (frame rules from two corners, masthead
letter-drop, coverlines rising out of line masks, sticker slap) are adapted from reel-kit fx/word-stamp and
fx/magazine-cover, Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md at the repository root).
Markup, layout, the slab fallback, colour sets and contracts are Reel Room's own.
"""
from comps_fx import _video
from heroes_base import (FPS, JS, Clock, Stage, box, esc, hero, make, prng, root, sfx, text_px)

STAMP_STEP = 2 / 30
NEQ_SVG = ('<svg class="ts-neq" viewBox="0 0 60 50" aria-hidden="true"><path class="n1" d="M6 18 H54" pathLength="1"/>'
           '<path class="n2" d="M6 33 H54" pathLength="1"/><path class="n3" d="M41 3 L19 47" pathLength="1"/></svg>')
TS_CSS = (".rrh-title-stamp .ts-blk{position:absolute;left:0;width:1080px;transform-origin:50% 60%}"
          ".rrh-title-stamp .ts-l{position:relative;width:1080px;text-align:center;white-space:nowrap;font-family:var(--k-fs);"
          "font-weight:900;line-height:1.04;letter-spacing:-.02em;color:var(--h-ink);text-transform:uppercase}"
          ".rrh-full.rrh-title-stamp .ts-l,.rrh-full.rrh-title-stamp .ts-sub{text-shadow:0 4px 26px rgba(0,0,0,.35)}"
          ".rrh-title-stamp:not(.rrh-full) .ts-l,.rrh-title-stamp:not(.rrh-full) .ts-sub{text-align:left;padding-left:72px}"
          ".rrh-title-stamp:not(.rrh-full) .ts-bar{margin-left:72px}"
          ".rrh-title-stamp:not(.rrh-full) .ts-c{transform-origin:0% 85%}"
          ".rrh-title-stamp .ts-w{display:inline-block;white-space:nowrap}"
          ".rrh-title-stamp .ts-c{display:inline-block;transform-origin:50% 85%}"
          ".rrh-title-stamp .ts-sub{position:relative;width:1080px;text-align:center;white-space:nowrap;font-family:var(--k-fs);"
          "font-style:italic;font-weight:600;line-height:1.02;letter-spacing:-.01em;color:var(--h-acc);margin-top:.34em}"
          ".rrh-title-stamp .ts-neq{display:inline-block;width:.78em;height:.62em;margin-right:.22em;vertical-align:.02em;overflow:visible}"
          ".rrh-title-stamp .ts-neq path{fill:none;stroke:var(--h-acc);stroke-width:6;stroke-linecap:round;stroke-dasharray:1}"
          ".rrh-title-stamp .ts-bar{display:block;margin:.36em auto 0;height:10px;border-radius:6px;background:var(--h-hl);"
          "transform-origin:0 50%}")


def _words_html(line, pid, li):
    out = []
    for wi, w in enumerate(line.split()):
        letters = "".join(f'<span class="ts-c">{esc(ch)}</span>' for ch in w)
        out.append(f'<span class="ts-w" id="{pid}w{li}_{wi}">{letters}</span>')
    return " ".join(out)


def _split_lines(text):
    words = str(text).split()
    if len(str(text)) <= 12 or len(words) < 2:
        return [str(text)]
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _ts_layout(lines, sub, stage, size):
    px = min(text_px(ln.upper(), 930, size or 260, k=0.78 if len(ln) <= 9 else 0.72, lo=70) for ln in lines)
    if stage.layout != "split":
        px = min(px, int(stage.h / (len(lines) * 0.98 + (0.75 if sub else 0) + 0.25)))
    sub_px = min(int(px * 0.62), text_px(sub or "x", 900, 150, k=0.5)) if sub else 0
    h = len(lines) * px * 1.04 + (sub_px * 1.14 if sub else 0) + 30
    top = round(stage.y0 + (stage.h - h) / 2)
    return px, sub_px, top, h


@hero("title-stamp", "title_stamp",
      fields={"text": ("text", (28, True)), "sub": ("text", (28, False)), "neq": ("bool", ()),
              "at": ("anchor", ()), "land": ("anchor", ()), "sub_at": ("anchor", ()), "until": ("anchor", ()),
              "tone": ("set", ()), "size": ("num", (110, 300))},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "any full-frame style (band above the head)"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["stamp the title", "big serif headline", "slam the headline in"],
      what="a huge serif headline stamps in letter by letter on its word over a colour-set shift, optional '≠' or "
           "italic sub-line, then holds and grows a hair", min_secs=1.4)
def title_stamp(self, text, sub=None, neq=False, at=0.0, land=None, sub_at=None, until=None, tone="dark",
                layout="split", area=None, size=None, z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    t_land = ck.at(land, 0.25, "stamp")
    t_text = t_in + 0.1 if t_land - t_in > 0.45 else max(t_in + 0.06, t_land - 0.06)   # never an empty panel
    lines = _split_lines(text)
    n_letters = sum(len(ln.replace(" ", "")) for ln in lines)
    step = min(STAMP_STEP, 0.62 / max(1, n_letters))
    t_built = t_text + step * n_letters + 0.2
    t_sub = ck.at(sub_at, t_built - t_in, "none", floor=t_text + 0.2) if sub else None
    t_out = ck.end(until, max(t_built, t_sub or 0, t_land) + 0.6)
    pid = self.uid("ts")
    px, sub_px, top, h = _ts_layout(lines, sub, stage, size)
    js = JS(pid)
    js.split = stage.layout == "split"
    rows = f"<style>#{pid} .ts-l{{font-size:{px}px}}</style>" + "".join(
        f'<div class="ts-l" data-fitgroup="{pid}" data-fitmax="930" {box("text", t_text + 0.2, t_out)}>'
        f'{_words_html(ln, pid, i)}</div>' for i, ln in enumerate(lines))
    if sub:
        rows += (f'<div class="ts-sub" style="font-size:{sub_px}px" {box("text", t_sub + 0.1, t_out)}>'
                 f'{NEQ_SVG if neq else ""}<span class="ts-sw">{esc(sub)}</span></div>')
    rows += f'<i class="ts-bar" style="width:{min(900, int(px * 2.6))}px"></i>'
    _ts_js(js, pid, stage, t_in, t_text, step, t_land, t_built, t_sub, neq, t_out)
    inner = f'<div class="ts-blk" style="top:{top}px">{rows}</div>'
    html = root(pid, "title-stamp", self, tone, inner + js.svg_defs(), stage,
                full=stage.layout != "split", extra_css=TS_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "colour set shift"), sfx(t_text, "stamp", f"title {text[:16]}")]
    ev += [sfx(t_sub, "pop", "sub-line")] if sub else []
    ev += [sfx(t_land, "impact", "title lands", "full")] if t_land > t_built else []
    meta = {"times": {"in": t_in, "text": t_text, "land": t_land, "sub": t_sub, "out": t_out}, "lines": lines,
            "px": px, "box": [70, top, 940, round(h)]}
    return make("title-stamp", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _ts_js(js, pid, stage, t_in, t_text, step, t_land, t_built, t_sub, neq, t_out):
    js.life(t_in, t_out + 0.24)
    if stage.layout == "split":
        js.ground_in(t_in, 0.42)
    js.hide(".ts-c", {"opacity": 0})
    js.ft(".ts-c", {"opacity": 0, "scale": 1.38, "yPercent": -6, "filter": "blur(2.5px)"},
          {"opacity": 1, "scale": 1, "yPercent": 0, "filter": "blur(0px)"}, t_text, 0.24, "back.out(1.4)", stagger=step)
    js.hide(".ts-bar", {"scaleX": 0})
    js.ft(".ts-bar", {"scaleX": 0}, {"scaleX": 1}, (t_sub + 0.12) if t_sub else max(t_land, t_built - 0.15) + 0.04,
          0.5, "expo.inOut")
    if t_land > t_built:
        js.ft(".ts-blk", {"scale": 1.06}, {"scale": 1}, t_land, 0.45, "elastic.out(1,0.45)")
    if t_sub is not None:
        js.hide(".ts-sub", {"opacity": 0})
        js.ft(".ts-sub", {"opacity": 0, "y": 40, "filter": "blur(10px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
              t_sub, 0.38, "expo.out")
        if neq:
            for i, d in ((1, 0.0), (2, 0.06), (3, 0.16)):
                js.hide(f".ts-neq .n{i}", {"strokeDashoffset": 1})
                js.ft(f".ts-neq .n{i}", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t_sub + d, 0.22, "power2.inOut")
    hold = max(t_land, t_built, t_sub or 0) + 0.45
    if t_out - hold > 0.3:
        js.ft(".ts-blk", {"scale": 1}, {"scale": 1.035}, hold, t_out - hold, "none")
    js.to(".ts-blk", {"opacity": 0, "y": -36, "filter": "blur(8px)"}, t_out, 0.22, "power3.in")


# ---------------------------------------------------------------------------------------------- word-stamp
WS_CSS = (".rrh-word-stamp .ws-slab{position:absolute;border-radius:44px;background:var(--h-card);box-shadow:var(--h-shadow);"
          "transform-origin:50% 50%}"
          ".rrh-word-stamp .ws-stack{position:absolute;left:0;width:1080px;display:flex;flex-direction:column;align-items:center}"
          ".rrh-word-stamp .ws-s{position:relative;display:inline-block;white-space:nowrap;font:700 56px/1.1 var(--k-fb);"
          "letter-spacing:-.01em;color:var(--h-ink);margin-bottom:28px}"
          ".rrh-word-stamp .ws-x{position:absolute;left:-10px;top:52%;width:calc(100% + 20px);height:7px;margin-top:-3px;"
          "border-radius:4px;background:var(--h-alert);transform-origin:0 50%}"
          ".rrh-word-stamp .ws-w{white-space:nowrap;font-family:var(--k-fd);font-weight:900;line-height:.86;"
          "letter-spacing:-.02em;word-spacing:.12em;color:var(--h-ink);text-transform:uppercase;transform-origin:50% 85%}"
          ".rrh-word-stamp .ws-c{display:inline-block;transform-origin:50% 85%}"
          ".rrh-word-stamp.rrh-full .ws-w,.rrh-word-stamp.rrh-full .ws-s{text-shadow:0 4px 30px rgba(0,0,0,.3)}"
          ".rrh-word-stamp .ws-matte{position:absolute;left:0;top:0;width:1080px;height:1920px}"
          ".rrh-word-stamp .ws-matte video{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}")


def _ws_geo(word, setup, stage, face, matte):
    fx, fy, fh = face
    if matte:                                  # behind the head: the head breaks the foot of the word
        px = text_px(word.upper(), 1000, 380, k=0.68, lo=140)
        bottom = fy - 0.42 * fh
        return px, None, round(bottom - px * 0.86 - (70 if setup else 0)), fx
    if stage.layout == "split":                # straight on the colour-set ground: the panel is the slab
        px = text_px(word.upper(), 940, 330, k=0.7, lo=110)
        return px, None, round(stage.y0 + (stage.h - (px * 0.86 + (80 if setup else 0))) / 2), 540
    px = text_px(word.upper(), 860, 240, k=0.7, lo=90)
    slab_h = min(stage.h, int(px * 0.86 + (90 if setup else 0) + 120))
    x, y, w, h = stage.fit(960, slab_h)
    return px, (x, y, w, h), round(y + (h - (px * 0.86 + (70 if setup else 0))) / 2), 540


@hero("word-stamp", "word_stamp",
      fields={"word": ("text", (12, True)), "setup": ("text", (30, False)), "strike": ("bool", ()),
              "at": ("anchor", ()), "setup_at": ("anchor", ()), "strike_at": ("anchor", ()), "until": ("anchor", ()),
              "tone": ("set", ())},
      fits=["any full-frame style with a cut-out (behind the head)", "split-deck / no matte: an in-front slab"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["stamp the word behind my head", "one huge word", "slam that word"],
      what="one huge word stamps in letter by letter (behind your head with a cut-out, else on a slab above it), a "
           "small set-up line sets above it and gets struck through", min_secs=1.4)
def word_stamp(self, word, setup=None, strike=False, at=0.0, setup_at=None, strike_at=None, until=None, tone="cream",
               layout="split", area=None, face=(540, 900, 200), matte=None, matte_start=0.0, track=None, z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at, "stamp")
    t_word = ck.t_in
    t_setup = min(ck.early(setup_at, -0.45), t_word - 0.2) if setup else None
    t_cap = self.until(until, t_word, 1.4, self.cursor(start=t_word)) - STAMP_STEP * len(word) - 0.75
    t_word = max(self.base, min(t_word, t_cap))     # built and read before the cut
    t_built = t_word + STAMP_STEP * (len(word) - 1) + 0.2
    t_strike = ck.at(strike_at, t_built - t_word + 0.15, "visual", floor=(t_setup or t_word) + 0.3) \
        if setup and strike else None
    t_in = min(t_word, t_setup or t_word)
    t_out = ck.end(until, max(t_built, t_strike or 0) + 0.6)
    px, slab, top, cxw = _ws_geo(word, setup, stage, face, matte)
    pid = self.uid("ws")
    js = JS(pid)
    js.split = stage.layout == "split"
    letters = "".join(f'<span class="ws-c">{esc(ch)}</span>' if ch != " " else " " for ch in word.upper())
    srow = (f'<div class="ws-s" {box("text", t_setup + 0.1, t_out)}>{esc(setup)}<i class="ws-x"></i></div>'
            if setup else "")
    stack = (f'<div class="ws-stack" style="top:{top}px;left:{cxw - 540}px">{srow}'
             f'<div class="ws-w" style="font-size:{px}px" {box("text", t_word + 0.15, t_out)}>{letters}</div></div>')
    slab_html = (f'<div class="ws-slab" style="left:{slab[0]}px;top:{slab[1]}px;width:{slab[2]}px;height:{slab[3]}px" '
                 f'{box("card", t_in, t_out, False)}></div>' if slab else "")
    matte_html = ""
    if matte:
        trk = track if track is not None else self.track(30)
        matte_html = _video(matte, t_in, t_out + 0.1, trk, -matte_start, cls="ws-matte")
    _ws_js(js, bool(slab), t_in, t_word, t_setup, t_strike, t_built, t_out,
           self.base if stage.layout == "split" and not matte else None)
    full = stage.layout != "split" or bool(matte)
    html = root(pid, "word-stamp", self, "dark" if matte else tone,
                slab_html + stack + matte_html, stage, full=full, extra_css=WS_CSS, z=z)
    ev = [sfx(t_word, "stamp", f"word {word}")] + ([sfx(t_setup, "pop", "set-up line", "full")] if setup else [])
    ev += [sfx(t_strike, "click", "strike")] if t_strike else []
    meta = {"times": {"in": t_in, "word": t_word, "setup": t_setup, "strike": t_strike, "out": t_out},
            "px": px, "mode": "behind" if matte else "slab", "box": list(slab) if slab else [60, top, 960, px]}
    return make("word-stamp", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _ws_js(js, slab, t_in, t_word, t_setup, t_strike, t_built, t_out, t_show=None):
    js.life(t_in if t_show is None else min(t_in, t_show), t_out + 0.24)    # a split panel is never empty
    if slab:
        js.ft(".ws-slab", {"opacity": 0, "scale": 0.9, "y": 50, "filter": "blur(12px)"},
              {"opacity": 1, "scale": 1, "y": 0, "filter": "blur(0px)"}, t_in, 0.42, "back.out(1.4)")
    js.hide(".ws-c", {"opacity": 0})
    js.ft(".ws-c", {"opacity": 0, "scale": 1.38, "yPercent": -6, "filter": "blur(6px)"},
          {"opacity": 1, "scale": 1, "yPercent": 0, "filter": "blur(0px)"}, t_word, 0.2, "power4.out", stagger=STAMP_STEP)
    if t_out - t_built > 0.3:
        js.ft(".ws-w", {"scale": 1}, {"scale": 1.035}, t_built, t_out - t_built, "none")
    if t_setup is not None:
        js.hide(".ws-s", {"opacity": 0})
        js.ft(".ws-s", {"opacity": 0, "y": 18, "filter": "blur(6px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
              t_setup, 0.3, "expo.out")
        js.hide(".ws-x", {"scaleX": 0})
        if t_strike:
            js.ft(".ws-x", {"scaleX": 0}, {"scaleX": 1}, t_strike, 0.24, "power2.inOut")
            js.to(".ws-s", {"opacity": 0.62}, t_strike + 0.1, 0.2, "power2.out")
    js.to(".ws-stack", {"opacity": 0, "y": -30, "filter": "blur(8px)"}, t_out, 0.22, "power3.in")
    if slab:
        js.to(".ws-slab", {"opacity": 0, "scale": 0.96}, t_out + 0.04, 0.2, "power3.in")


# ---------------------------------------------------------------------------------------------- magazine-cover
MC_CSS = (".rrh-magazine-cover .mc-rule{position:absolute;display:block;background:var(--h-hl)}"
          ".rrh-magazine-cover .mc-mh{position:absolute;left:0;width:1080px;text-align:center;white-space:nowrap;"
          "font-family:var(--k-fs);font-weight:900;line-height:.82;letter-spacing:-.03em;color:var(--h-ink);"
          "text-transform:uppercase;text-shadow:0 4px 30px rgba(0,0,0,.28)}"
          ".rrh-magazine-cover .mc-c{display:inline-block}"
          ".rrh-magazine-cover .mc-col{position:absolute;width:300px;padding:18px 0}"
          ".rrh-magazine-cover .mc-col.r{width:330px}"
          ".rrh-magazine-cover .mc-col::before{content:'';position:absolute;left:-40px;right:-40px;top:-30px;bottom:-30px;"
          "z-index:-1;border-radius:30px;background:radial-gradient(closest-side,rgba(0,0,0,.7),rgba(0,0,0,0))}"
          ".rrh-magazine-cover .mc-col.r{text-align:right}"
          ".rrh-magazine-cover .mc-m{overflow:hidden;padding:4px 0}"
          ".rrh-magazine-cover .mc-k{display:block;font:600 22px/1.1 var(--h-fm);letter-spacing:.16em;text-transform:uppercase;"
          "color:var(--h-hl);white-space:nowrap;text-shadow:0 2px 12px rgba(0,0,0,.6)}"
          ".rrh-magazine-cover .mc-k::before{content:'';display:block;width:46px;height:6px;margin-bottom:12px;background:var(--h-hl)}"
          ".rrh-magazine-cover .mc-col.r .mc-k::before{margin-left:auto}"
          ".rrh-magazine-cover .mc-m:nth-child(2) .mc-t{font-family:var(--k-fs);font-style:italic;font-weight:700}"
          ".rrh-magazine-cover .mc-t{display:block;font:900 48px/1.08 var(--k-fd);word-spacing:.12em;letter-spacing:-.02em;color:var(--h-ink);"
          "white-space:nowrap;text-shadow:0 2px 18px rgba(0,0,0,.7),0 1px 3px rgba(0,0,0,.5)}"
          ".rrh-magazine-cover .mc-bc{position:absolute;width:150px;height:96px;padding:12px;border-radius:4px;background:var(--h-ink);"
          "display:flex;align-items:stretch}"
          ".rrh-magazine-cover .mc-bc i{display:block;flex:none;background:var(--h-g)}"
          ".rrh-magazine-cover .mc-st{position:absolute;width:200px;height:200px;border-radius:50%;background:var(--h-hl);"
          "display:flex;align-items:center;justify-content:center;box-shadow:0 16px 34px rgba(0,0,0,.35),"
          "inset 0 0 0 8px var(--h-hl),inset 0 0 0 11px rgba(0,0,0,.85)}"
          ".rrh-magazine-cover .mc-st b{font:900 60px/1 var(--k-fd);letter-spacing:-.02em;color:#111;white-space:nowrap}")


def _barcode(seed=7):
    r = prng(seed)
    out, w = [], 0
    while w < 120:
        bw = 2 if w < 4 or w > 114 else 1 + int(r() * 4)
        gw = 1 + int(r() * 3)
        out.append(f'<i style="width:{bw}px;margin-right:{gw}px"></i>')
        w += bw + gw
    return "".join(out)


def _mc_geo(face, n_left, area, matte=False):
    fx, fy, fh = face
    head_top = fy - 0.7 * fh
    mast_px = 230
    if not matte:            # no cut-out: the masthead sits fully above the head, never over the forehead
        mast_px = int(max(110, min(230, (head_top - 24 - 250) / 0.82)))
        mast_top = max(250, round(head_top - 24 - mast_px * 0.82))
    else:
        mast_top = max(250, min(round(head_top - mast_px * 0.55), 420))
    if area:
        mast_top = max(250, min(mast_top, area[1] - mast_px))
    col_top = round(fy + 0.15 * fh)
    lx, rx = max(64, round(fx - fh * 0.9 - 300)), min(690, round(fx + fh * 0.9))
    return mast_px, mast_top, col_top, lx, rx


@hero("magazine-cover", "magazine_cover",
      fields={"mast": ("text", (12, True)), "lines": ("texts", (2, 4, 22)), "kicker": ("text", (18, False)),
              "sticker": ("text", (8, False)), "at": ("anchor", ()), "lines_at": ("anchors", (2,)),
              "sticker_at": ("anchor", ()), "until": ("anchor", ())},
      fits=["split-deck (full-frame beat)", "any full-frame style", "best with a cut-out (masthead behind the head)"],
      layouts=["full", "overlay"], split_mode="full",
      say=["make it a magazine cover", "put me on the cover"],
      what="the frame becomes a magazine cover: rules draw, the masthead drops in letter by letter, coverlines rise "
           "beside your head on their words, a barcode prints and a sticker slaps on", min_secs=2.2)
def magazine_cover(self, mast, lines, kicker=None, sticker=None, at=0.0, lines_at=None, sticker_at=None, until=None,
                   tone="dark", layout="full", area=None, face=(540, 900, 200), matte=None, matte_start=0.0,
                   track=None, z=None):
    ck = Clock(self, at)
    t_in = ck.t_in
    la = list(lines_at or [])
    t_l = ck.at(la[0] if la else None, 0.75, "visual", floor=t_in + 0.45)
    t_r = ck.at(la[1] if len(la) > 1 else None, t_l - t_in + 0.3, "visual", floor=t_l + 0.12)
    t_st = ck.at(sticker_at, t_r - t_in + 0.35, "stamp", floor=t_r + 0.15) if sticker else None
    t_out = ck.end(until, max(t_r, t_st or 0) + 0.8)
    pid = self.uid("mc")
    js = JS(pid)
    mast_px, mast_top, col_top, lx, rx = _mc_geo(face, len(lines), area, bool(matte))
    mast_px = min(mast_px, text_px(mast.upper(), 960, 230, k=0.7, lo=110))
    half = (len(lines) + 1) // 2
    cols = [lines[:half], lines[half:]]
    html_cols = ""
    for ci, (col, x) in enumerate(zip(cols, (lx, rx))):
        if not col:
            continue
        t0 = t_l if ci == 0 else t_r
        rows = (f'<div class="mc-m"><span class="mc-k" {box("text", t0 + 0.1, t_out)}>{esc(kicker)}</span></div>'
                if kicker and ci == 0 else "")
        rows += "".join(f'<div class="mc-m"><span class="mc-t" {box("text", t0 + 0.15, t_out)}>{esc(s)}</span></div>'
                        for s in col)
        html_cols += f'<div class="mc-col{" r" if ci else ""} c{ci}" style="left:{x}px;top:{col_top}px">{rows}</div>'
    letters = "".join(f'<span class="mc-c">{esc(ch) if ch != " " else "&nbsp;"}</span>' for ch in mast.upper())
    rules = "".join(f'<i class="mc-rule {k}" style="{s}"></i>' for k, s in (
        ("rt", "left:40px;top:236px;width:1000px;height:4px;transform-origin:0 0"),
        ("rb", "left:40px;top:1462px;width:1000px;height:4px;transform-origin:100% 0"),
        ("rl", "left:40px;top:236px;width:4px;height:1230px;transform-origin:0 0"),
        ("rr", "left:1036px;top:236px;width:4px;height:1230px;transform-origin:0 100%"),
        ("rt i2", "left:56px;top:252px;width:968px;height:2px;transform-origin:0 0"),
        ("rb i2", "left:56px;top:1448px;width:968px;height:2px;transform-origin:100% 0")))
    inner = (rules + f'<div class="mc-mh" style="top:{mast_top}px;font-size:{mast_px}px" '
             f'{box("text", t_in + 0.4, t_out)}>{letters}</div>' + html_cols
             + f'<div class="mc-bc" style="left:{lx}px;top:1300px">{_barcode()}</div>'
             + (f'<div class="mc-st" style="left:{min(rx + 60, 770)}px;top:1150px"><b {box("glyph", t_st, t_out)}>'
                f'{esc(sticker)}</b></div>' if sticker else ""))
    if matte:
        trk = track if track is not None else self.track(30)
        inner += _video(matte, t_in, t_out + 0.1, trk, -matte_start, cls="ws-matte")
    _mc_js(js, mast, t_in, t_l, t_r, t_st, t_out, bool(cols[1]))
    html = root(pid, "magazine-cover", self, tone, inner, Stage("full", area), full=True,
                extra_css=MC_CSS + WS_CSS.replace("rrh-word-stamp", "rrh-magazine-cover"), z=z)
    ev = [sfx(t_in, "whoosh", "cover frame"), sfx(t_in + 0.1, "stamp", "masthead"), sfx(t_l, "pop", "coverlines")]
    ev += [sfx(t_st, "stamp", "sticker")] if t_st else []
    meta = {"times": {"in": t_in, "left": t_l, "right": t_r, "sticker": t_st, "out": t_out},
            "box": [40, 236, 1000, 1230], "mast_px": mast_px, "cols": [lx, rx, col_top]}
    return make("magazine-cover", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _mc_js(js, mast, t_in, t_l, t_r, t_st, t_out, has_right):
    js.life(t_in, t_out + 0.24)
    js.ft(".mc-rule.rt,.mc-rule.rb", {"scaleX": 0}, {"scaleX": 1}, t_in, 0.5, "expo.out")
    js.ft(".mc-rule.rl,.mc-rule.rr", {"scaleY": 0}, {"scaleY": 1}, t_in, 0.5, "expo.out")
    n = len(mast.replace(" ", ""))
    js.hide(".mc-c", {"opacity": 0})
    js.ft(".mc-c", {"opacity": 0, "yPercent": -70, "filter": "blur(8px)"},
          {"opacity": 1, "yPercent": 0, "filter": "blur(0px)"}, t_in + 0.06, 0.36, "back.out(1.4)",
          stagger=min(0.05, 0.5 / max(1, n)))
    for ci, t in ((0, t_l), (1, t_r)):
        if ci == 1 and not has_right:
            continue
        js.hide(f".c{ci} .mc-m > span", {"yPercent": 110})
        js.ft(f".c{ci} .mc-m > span", {"yPercent": 110}, {"yPercent": 0}, t, 0.34, "expo.out", stagger=0.06)
    js.hide(".mc-bc", {"clipPath": "inset(0% 100% 0% 0%)"})
    js.ft(".mc-bc", {"clipPath": "inset(0% 100% 0% 0%)"}, {"clipPath": "inset(0% 0% 0% 0%)"}, t_l - 0.1, 0.3, "power2.out")
    if t_st:
        js.hide(".mc-st", {"opacity": 0})
        js.ft(".mc-st", {"opacity": 0, "scale": 2.2, "rotation": 40, "filter": "blur(8px)"},
              {"opacity": 1, "scale": 1, "rotation": -10, "filter": "blur(0px)"}, t_st, 0.42, "back.out(2.2)")
        js.lines.append(f"tl.to({js.s('.mc-st')},{{scale:1.08,duration:.08,yoyo:true,repeat:1,ease:'power2.out'}},{t_st + 0.42:.4f});")
    js.to(".mc-mh,.mc-col,.mc-bc,.mc-st", {"opacity": 0, "y": -24, "filter": "blur(6px)"}, t_out, 0.2, "power3.in")
    js.to(".mc-rule", {"opacity": 0}, t_out, 0.2, "power3.in")
