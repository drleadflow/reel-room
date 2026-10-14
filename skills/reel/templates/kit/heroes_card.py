"""heroes_card: video-card. A course / walkthrough card unfolds from its centre: a vertical player on the left (the
creator's own reel thumbnails, one per chapter, each with a slow push; a frame-synced copy of the plate when there
are none), the title and a chapter list on the right. Play presses on its word and blows out, each chapter lights on
its word (the row fills, the number flips to a check when it is done), the scrubber fills segment by segment, then
the card folds shut into its centre.

The centre unfold (clip-path inset 42% 44%), the play press and the chapter skip with a filling scrubber are adapted
from reel-kit fx/video-card, Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md at the
repository root). Layout, the chapter list, colour sets and the contract are Reel Room's own.
"""
from comps_fx import _video
from heroes_base import JS, Clock, Stage, box, colour_set, esc, hero, make, root, sfx, text_px

VC_CSS = (".rrh-video-card .vc-card{position:absolute;border-radius:34px;overflow:hidden;background:var(--h-card);"
          "box-shadow:var(--h-shadow);transform-origin:50% 50%}"
          ".rrh-video-card .vc-th{position:absolute;left:22px;top:22px;bottom:22px;border-radius:22px;overflow:hidden;"
          "background:#000}"
          ".rrh-video-card .vc-f{position:absolute;inset:0;transform-origin:50% 40%}"
          ".rrh-video-card .vc-f img,.rrh-video-card .vc-f video{position:absolute;left:0;top:0;width:100%;height:100%;"
          "object-fit:cover}"
          ".rrh-video-card .vc-f .k-vid{position:absolute;inset:0}"
          ".rrh-video-card .vc-dim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 55%,rgba(0,0,0,.55))}"
          ".rrh-video-card .vc-flash{position:absolute;inset:0;background:#fff;opacity:0}"
          ".rrh-video-card .vc-play{position:absolute;left:26px;bottom:56px;width:104px;height:104px;border-radius:52px;"
          "background:var(--h-hl);display:flex;align-items:center;justify-content:center;box-shadow:0 12px 26px rgba(0,0,0,.35)}"
          ".rrh-video-card .vc-play svg{width:44px;height:44px;margin-left:6px}"
          ".rrh-video-card .vc-play path{fill:#111}"
          ".rrh-video-card .vc-bar{position:absolute;left:22px;right:22px;bottom:22px;height:10px}"
          ".rrh-video-card .vc-seg{position:absolute;top:0;height:10px;border-radius:5px;background:rgba(255,255,255,.35);overflow:hidden}"
          ".rrh-video-card .vc-seg i{position:absolute;inset:0;border-radius:5px;background:var(--h-hl);transform-origin:0 50%}"
          ".rrh-video-card .vc-col{position:absolute;top:44px;right:40px}"
          ".rrh-video-card .vc-k{font:600 22px/1 var(--h-fm);letter-spacing:.16em;text-transform:uppercase;color:var(--h-sub);"
          "white-space:nowrap}"
          ".rrh-video-card .vc-ttl{margin-top:14px;font-family:var(--k-fs);font-weight:800;line-height:1.08;color:var(--h-ink);"
          "white-space:nowrap;letter-spacing:-.01em}"
          ".rrh-video-card .vc-ch{position:relative;height:84px;margin-top:14px;border-radius:20px;display:flex;align-items:center;"
          "gap:20px;padding:0 20px;white-space:nowrap}"
          ".rrh-video-card .vc-hl{position:absolute;inset:0;border-radius:20px;background:var(--h-acc);transform-origin:0 50%}"
          ".rrh-video-card .vc-n{position:relative;width:52px;height:52px;border-radius:26px;border:3px solid var(--h-line);"
          "display:flex;align-items:center;justify-content:center;font:700 24px/1 var(--h-fm);color:var(--h-sub)}"
          ".rrh-video-card .vc-l{position:relative;font:700 38px/1 var(--k-fb);letter-spacing:-.01em;color:var(--h-sub)}")
PLAY = '<svg viewBox="0 0 40 40"><path d="M10 5 L35 20 L10 35 Z"/></svg>'
FRAMING = [(1.0, 0, 0), (1.3, -20, 40), (1.6, 30, 80), (1.15, 0, -20)]


def _vc_times(ck, play_at, chapter_at, n):
    t_play = ck.at(play_at, 0.55, "visual", floor=ck.t_in + 0.45)
    ca = list(chapter_at or [])
    starts, prev = [], t_play
    for i in range(n):
        t = ck.at(ca[i] if i < len(ca) else None, prev - ck.t_in + (0.15 if i == 0 else 0.8), "visual",
                  floor=prev + (0.0 if i == 0 else 0.45))
        starts.append(t)
        prev = t
    return t_play, starts


def _frames(clips, src, t_in, t_out, trk, n):
    """One frame per chapter: the creator's own thumbnails when given, else one plate copy reframed per chapter."""
    if clips:
        return "".join(f'<div class="vc-f f{i}"><img src="{esc(clips[i % len(clips)])}" alt=""></div>' for i in range(n)), True
    return f'<div class="vc-f f0">{_video(src, t_in, t_out, trk, 0.0)}</div>', False


@hero("video-card", "video_card",
      fields={"title": ("text", (28, True)), "chapters": ("texts", (2, 4, 18)), "at": ("anchor", ()),
              "play_at": ("anchor", ()), "chapter_at": ("anchors", (4,)), "until": ("anchor", ()),
              "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "full-frame styles (band above the head)"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["show the walkthrough video", "play the video card", "show the course chapters"],
      what="a course card unfolds: a vertical player of your own reels on the left, the title and chapter list on the "
           "right; play presses on your word, each chapter lights on its word while the scrubber fills, then it folds",
      min_secs=2.2)
def video_card(self, title, chapters, at=0.0, play_at=None, chapter_at=None, until=None, clips=None,
               src="assets/aroll.mp4", tone="cream", layout="split", area=None, track=None, z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    n = len(chapters)
    t_play, starts = _vc_times(ck, play_at, chapter_at, n)
    t_out = ck.end(until, starts[-1] + 0.8)
    t_fold = max(starts[-1] + 0.5, t_out - 0.34)
    pid = self.uid("vc")
    js = JS(pid)
    js.split = stage.layout == "split"
    x, y, cw, h = stage.fit(960, 620)
    tw = round((h - 44) * 9 / 16)
    trk = track if track is not None else self.track(30)
    frames, stills = _frames(clips, src, t_in, t_out, trk, n)
    segs, sx, gap = [], 0, 6
    for i in range(n):
        sw = (tw - 44 - gap * (n - 1)) / n
        segs.append(f'<div class="vc-seg" style="left:{sx:.0f}px;width:{sw:.0f}px"><i class="s{i}"></i></div>')
        sx += sw + gap
    col_w = cw - tw - 22 - 40 - 44
    tpx = text_px(title, col_w, 60, k=0.5, lo=34)
    rows = "".join(f'<div class="vc-ch c{i}"><i class="vc-hl"></i><span class="vc-n">{i + 1:02d}</span>'
                   f'<span class="vc-l" {box("text", starts[i], t_fold)}>{esc(ch)}</span></div>' for i, ch in enumerate(chapters))
    inner = (f'<div class="vc-card" id="{pid}c" style="left:{x}px;top:{y}px;width:{cw}px;height:{h}px" {box("card", t_in, t_fold, False)}>'
             f'<div class="vc-th" style="width:{tw}px">{frames}<div class="vc-dim"></div><div class="vc-flash"></div>'
             f'<div class="vc-play">{PLAY}</div><div class="vc-bar">{"".join(segs)}</div></div>'
             f'<div class="vc-col" style="width:{col_w}px"><div class="vc-ttl" style="font-size:{tpx}px" '
             f'{box("text", t_in + 0.2, t_fold)}>{esc(title)}</div>{rows}</div></div>')
    _vc_js(js, pid, t_in, t_play, starts, t_fold, t_out, n, stills, colour_set(self, tone)["g"])
    html = root(pid, "video-card", self, tone, inner, stage, full=stage.layout != "split", extra_css=VC_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "card unfolds"), sfx(t_play, "click", "play"), sfx(t_fold, "whoosh", "card folds", "full")]
    ev += [sfx(t, "tick", f"chapter {i + 1}") for i, t in enumerate(starts)]
    meta = {"times": {"in": t_in, "play": t_play, "chapters": starts, "fold": t_fold, "out": t_out}, "box": [x, y, cw, h],
            "track": trk}
    return make("video-card", self, pid, html, js, ev, t_in, t_out + 0.1, meta)


def _vc_js(js, pid, t_in, t_play, starts, t_fold, t_out, n, stills, on):
    js.life(t_in, t_out)
    js.ground_in(t_in, 0.4)
    c = f"#{pid}c"
    shut, opn = "inset(42% 44% 42% 44% round 34px)", "inset(0% 0% 0% 0% round 34px)"
    js.ft(c, {"opacity": 0, "scale": 0.92, "clipPath": shut}, {"opacity": 1, "scale": 1, "clipPath": opn},
          t_in + 0.04, 0.46, "expo.out")
    js.ft(".vc-ttl", {"opacity": 0, "y": 30, "filter": "blur(6px)"}, {"opacity": 1, "y": 0, "filter": "blur(0px)"},
          t_in + 0.16, 0.4, "expo.out")
    for i in range(n):              # each chapter row arrives on its own word, then lights
        js.ft(f".c{i}", {"opacity": 0, "x": 40, "filter": "blur(6px)"}, {"opacity": 1, "x": 0, "filter": "blur(0px)"},
              starts[i] - 0.12, 0.36, "back.out(1.4)")
    js.hide(".vc-hl", {"scaleX": 0})
    js.ft(".vc-play", {"opacity": 0, "scale": 0.4}, {"opacity": 1, "scale": 1}, t_in + 0.3, 0.32, "back.out(2.2)")
    js.ft(".vc-play", {"scale": 1}, {"scale": 0.84}, t_play, 0.07, "power2.in")
    js.to(".vc-play", {"scale": 1.4, "opacity": 0}, t_play + 0.07, 0.22, "power2.out")
    js.hide(".vc-seg i", {"scaleX": 0})
    if stills:
        js.hide(".vc-f", {"opacity": 0})
        js.set(".f0", {"opacity": 1}, t_in)
    for i, t in enumerate(starts):
        end = starts[i + 1] if i + 1 < n else t_fold
        sel = f".f{i}" if stills else ".f0"
        s, dx, dy = (1.0, 0, 0) if stills else FRAMING[i % len(FRAMING)]
        if stills and i:
            js.set(f".f{i}", {"opacity": 1}, t)
            js.set(f".f{i - 1}", {"opacity": 0}, t)
        js.set(sel, {"scale": s, "x": dx, "y": dy}, t)
        js.ft(sel, {"scale": s}, {"scale": s * 1.08}, t, max(0.3, end - t + 0.2), "none")
        if i:
            js.ft(".vc-flash", {"opacity": 0.8}, {"opacity": 0}, t, 0.18, "power2.out")
            js.set(f".s{i - 1}", {"scaleX": 1}, t)
            js.to(f".c{i - 1} .vc-hl", {"opacity": 0.22}, t, 0.25, "power2.out")
            js.set(f".c{i - 1} .vc-n", {"textContent": "✓"}, t)
        js.ft(f".c{i} .vc-hl", {"scaleX": 0}, {"scaleX": 1}, t, 0.34, "expo.out")
        js.to(f".c{i} .vc-l", {"color": on}, t + 0.04, 0.2, "power2.out")
        js.to(f".c{i} .vc-n", {"color": on, "borderColor": on}, t + 0.04, 0.2, "power2.out")
        js.ft(f".s{i}", {"scaleX": 0}, {"scaleX": 1 if i == n - 1 else 0.85}, t, max(0.3, end - t), "none")
    js.to(c, {"clipPath": "inset(42% 44% 42% 44% round 34px)", "scale": 0.94}, t_fold, t_out - t_fold, "power3.in")
    js.set(c, {"opacity": 0}, t_out)
