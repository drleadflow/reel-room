"""heroes_edit: editing / product heroes. nle-timeline (an editing timeline of THIS video builds on the words:
clips, captions, graphics, waveform, sound effects, a playhead with a running timecode, then it folds to a line)
and palette-fan (style swatches fan out like a paint deck, each a live thumbnail with a name along
its strip, the picked one lifts on the word).

nle-timeline's open-from-a-line / lanes-by-beat / per-frame timecode / fold-to-a-line sequence is adapted from
reel-kit fx/nle-timeline, Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md at the
repository root). The data model, markup, colour sets and contracts are Reel Room's own; palette-fan is our own.
"""
import os

from comps_fx import _video
from heroes_base import (FPS, JS, Clock, Stage, box, colour_set, esc, hero, make, prng, rgba, root, sfx, mix)

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def _media(src, t0, t1, track, cls, style=""):
    """An image, or a video playing from its start at t0 (own wrapper, coverage-safe)."""
    if str(src).lower().endswith(IMG_EXT):
        return f'<div class="{cls}"><img src="{esc(src)}" alt="" style="{style}"></div>'
    return _video(src, t0, t1, track, -round(t0 * FPS) / FPS, cls=cls)


# ---------------------------------------------------------------------------------------------- nle-timeline
NL_CSS = (".rrh-nle-timeline .nl-card{position:absolute;border-radius:28px;overflow:hidden;box-shadow:var(--h-shadow);"
          "transform-origin:50% 50%}"
          ".rrh-nle-timeline .nl-head{position:absolute;left:0;right:0;top:0;height:84px;display:flex;align-items:center;gap:16px;"
          "padding:0 30px}"
          ".rrh-nle-timeline .nl-dot{width:20px;height:20px;border-radius:10px;display:inline-block}"
          ".rrh-nle-timeline .nl-ttl{margin-left:14px;font:800 40px/1 var(--k-fd);letter-spacing:-.01em;white-space:nowrap}"
          ".rrh-nle-timeline .nl-tc{margin-left:auto;font:700 44px/1 var(--h-fm);letter-spacing:.02em;white-space:nowrap}"
          ".rrh-nle-timeline .nl-ruler{position:absolute;left:168px;right:30px;top:86px;height:38px}"
          ".rrh-nle-timeline .nl-ruler i{position:absolute;bottom:4px;width:2px;border-radius:1px}"
          ".rrh-nle-timeline .nl-lane{position:absolute;left:0;right:0;height:88px;transform-origin:50% 50%}"
          ".rrh-nle-timeline .nl-lh{position:absolute;left:22px;top:28px;font:800 28px/34px var(--h-fm);letter-spacing:.06em;"
          "white-space:nowrap}"
          ".rrh-nle-timeline .nl-bl{position:absolute;top:10px;height:68px;border-radius:9px;transform-origin:0 50%}"
          ".rrh-nle-timeline .nl-cap{position:absolute;top:30px;height:28px;border-radius:5px;transform-origin:50% 50%}"
          ".rrh-nle-timeline .nl-w{position:absolute;bottom:44px;width:6px;border-radius:3px;transform-origin:50% 100%}"
          ".rrh-nle-timeline .nl-sfx{position:absolute;top:30px;width:28px;height:28px;transform:rotate(45deg);border-radius:4px}"
          ".rrh-nle-timeline .nl-ph{position:absolute;top:86px;width:4px;margin-left:-2px;border-radius:2px}"
          ".rrh-nle-timeline .nl-ph::before{content:'';position:absolute;left:-12px;top:-2px;width:28px;height:22px;"
          "border-radius:6px 6px 14px 14px;background:inherit}")
LANES = ("T1", "V2", "V1", "A1", "A2")
LANE_NAMES = {"T1": "TEXT", "V2": "FX", "V1": "VIDEO", "A1": "VOICE", "A2": "SFX"}
LX = 168            # lanes start after the lane names
LANE_H = 96


def _nl_data(words, span, cuts, caps, blocks, sfx_t, wave):
    """Defaults from the words: caption chunks of 3 words, cuts at pauses, a speech envelope, graphics every ~2 s."""
    lo, hi = span
    ws = [w for w in words if lo - 0.01 <= w["start"] < hi]
    if caps is None:
        caps = [(ws[i]["start"], ws[min(i + 2, len(ws) - 1)]["end"]) for i in range(0, len(ws), 3)]
    if cuts is None:
        cuts = [b["start"] for a, b in zip(ws, ws[1:]) if b["start"] - a["end"] > 0.22]
    if wave is None:
        r = prng(len(ws) + 3)
        wave = []
        n = 120
        for k in range(n):
            t = lo + (hi - lo) * (k + .5) / n
            on = any(w["start"] - .04 <= t <= w["end"] + .04 for w in ws)
            wave.append(round((0.35 + 0.65 * r()) if on else 0.06 * r(), 3))
    if blocks is None:
        step = max(1.2, (hi - lo) / 4)
        blocks = [(lo + i * step + 0.1, lo + i * step + step * 0.62) for i in range(int((hi - lo) / step))]
    if sfx_t is None:
        sfx_t = [b[0] for b in blocks] + cuts[:6]
    return cuts, caps, blocks, sfx_t, wave


def _nl_lanes(x0, x1, lo, hi, d, pal, thumbs=None):
    cuts, caps, blocks, sfx_t, wave = d
    X = lambda t: x0 + (x1 - x0) * (min(hi, max(lo, t)) - lo) / max(1e-6, hi - lo)  # noqa: E731
    out = {}
    out["T1"] = "".join(f'<i class="nl-cap" style="left:{X(a):.0f}px;width:{max(6, X(b) - X(a) - 3):.0f}px;'
                        f'background:{pal["hl"]}"></i>' for a, b in caps)
    out["V2"] = "".join(f'<i class="nl-bl fx" style="left:{X(a):.0f}px;width:{max(14, X(b) - X(a)):.0f}px;'
                        f'background:{pal["acc"]}"></i>' for a, b in blocks)
    edges = [lo] + [c for c in cuts if lo < c < hi] + [hi]
    th = list(thumbs or [])
    out["V1"] = "".join(f'<i class="nl-bl clip" style="left:{X(a) + 2:.0f}px;width:{max(8, X(b) - X(a) - 4):.0f}px;'
                        f'background:{pal["clip"][i % 2]}'
                        + (f' url({esc(th[i % len(th)])}) center 30%/cover' if th else "") + '"></i>'
                        for i, (a, b) in enumerate(zip(edges, edges[1:])))
    n = len(wave)
    out["A1"] = "".join(f'<i class="nl-w" style="left:{x0 + (x1 - x0) * (k + .5) / n - 3:.0f}px;'
                        f'background:{pal["wave"]};height:{6 + 62 * v:.0f}px"></i>' for k, v in enumerate(wave))
    out["A2"] = "".join(f'<i class="nl-sfx" style="left:{X(t) - 14:.0f}px;background:{pal["alert"]}"></i>'
                        for t in sfx_t if lo <= t <= hi)
    return out


def _nl_pal(kit, tone="cream"):
    d = colour_set(kit, "dark")
    c = kit.brand["colors"]
    return {"card": mix(c["ink"], c["bg"], .8) if tone == "dark" else d["g2"], "ink": d["ink"], "sub": d["sub"], "lane": rgba(c["bg"], .05), "hl": c.get("highlight", c["accent"]),
            "acc": mix(c["accent"], "#ffffff", .8), "clip": (mix(c["bg"], c["ink"], .78), mix(c["bg"], c["ink"], .62)),
            "wave": mix(c["accent"], c["bg"], .55), "alert": c.get("alert", c["accent"]), "tick": rgba(c["bg"], .3)}


def _nl_tc(t):
    f = int(round(t * FPS))
    return f"00:{f // 1800:02d}:{(f // 30) % 60:02d}:{f % 30:02d}"


@hero("nle-timeline", "nle_timeline",
      fields={"title": ("text", (28, False)), "at": ("anchor", ()), "land": ("anchor", ()), "until": ("anchor", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "full-frame styles (band above the head)"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["show the editing timeline", "show how much editing this was", "timeline of this video"],
      what="a real editing timeline of THIS video builds on your words (clips, captions, graphics, waveform, sound "
           "effects), a playhead tears across with a running timecode, then it folds to a line", min_secs=1.6)
def nle_timeline(self, title=None, at=0.0, land=None, until=None, span=None, cuts=None, caps=None, blocks=None,
                 sfx_times=None, wave=None, thumbs=None, tone="cream", layout="split", area=None, z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    t_land = ck.at(land, 1.1, "visual", floor=t_in + 0.6)
    t_out = ck.end(until, t_land + 0.8)
    t_fold = max(t_land + 0.3, t_out - 0.5)
    words = self.words
    span = span or ((words[0]["start"], words[-1]["end"]) if words else (0.0, 10.0))
    d = _nl_data(words, span, cuts, caps, blocks, sfx_times, wave)
    pal = _nl_pal(self, tone)
    pid = self.uid("nl")
    js = JS(pid)
    js.split = stage.layout == "split"
    cw, lane_top = 980, 128
    ch = lane_top + 5 * LANE_H + 24
    x, y, w, h = stage.fit(cw, ch)
    lanes = _nl_lanes(LX, cw - 30, span[0], span[1], d, pal, thumbs)
    rows = "".join(f'<div class="nl-lane L{n}" style="top:{lane_top + i * LANE_H}px;background:{pal["lane"]}">'
                   f'<span class="nl-lh" style="color:{pal["sub"]}" {box("text", t_in + 0.2, t_fold)}>{LANE_NAMES[n]}</span>'
                   f'{lanes[n]}</div>' for i, n in enumerate(LANES))
    ticks = "".join(f'<i style="left:{k * (cw - LX - 30) / 40:.0f}px;height:{16 if k % 5 == 0 else 8}px;background:{pal["tick"]}"></i>'
                    for k in range(41))
    head = (f'<div class="nl-head" style="color:{pal["ink"]}">'
            + "".join(f'<i class="nl-dot" style="background:{c}"></i>' for c in (pal["alert"], pal["hl"], pal["acc"]))
            + (f'<span class="nl-ttl" {box("text", t_in + 0.2, t_fold)}>{esc(title)}</span>' if title else "")
            + f'<span class="nl-tc" id="{pid}tc" {box("glyph", t_in + 0.2, t_fold)}>{_nl_tc(0)}</span></div>')
    ph = f'<i class="nl-ph" id="{pid}ph" style="left:{LX}px;height:{ch - 80}px;background:{pal["alert"]}"></i>'
    inner = (f'<div class="nl-card" id="{pid}c" style="left:{x}px;top:{y}px;width:{cw}px;height:{ch}px;background:{pal["card"]}" '
             f'{box("card", t_in, t_fold, False)}>{head}<div class="nl-ruler">{ticks}</div>{rows}{ph}</div>')
    steps = [t_in + 0.25 + (t_land - t_in - 0.25) * k / 3 for k in range(4)]
    _nl_js(js, pid, t_in, steps, t_fold, t_out, span, cw - LX - 30)
    html = root(pid, "nle-timeline", self, tone, inner + js.svg_defs(), stage, full=stage.layout != "split",
                extra_css=NL_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "timeline opens"), sfx(steps[0], "pop", "clips land"), sfx(steps[2], "tick", "captions", "full"),
          sfx(t_fold, "whoosh", "timeline folds")]
    meta = {"times": {"in": t_in, "steps": steps, "land": t_land, "fold": t_fold, "out": t_out}, "box": [x, y, cw, ch],
            "span": list(span), "cuts": len(d[0])}
    return make("nle-timeline", self, pid, html, js, ev, t_in, t_out + 0.1, meta)


def _nl_js(js, pid, t_in, steps, t_fold, t_out, span, travel):
    js.life(t_in, t_out)
    js.ground_in(t_in, 0.4)
    c = f"#{pid}c"
    js.ft(c, {"opacity": 0, "scaleY": 0.01, "scaleX": 0.86, "filter": "blur(8px)"},
          {"opacity": 1, "scaleY": 1, "scaleX": 1, "filter": "blur(0px)"}, t_in + 0.05, 0.34, "expo.out")
    js.hide(".nl-bl.clip", {"scaleX": 0})
    js.ft(".nl-bl.clip", {"scaleX": 0}, {"scaleX": 1}, steps[0], 0.22, "power3.out", stagger=0.02)
    js.hide(".nl-w", {"scaleY": 0})
    js.ft(".nl-w", {"scaleY": 0}, {"scaleY": 1}, steps[0] + 0.06, 0.2, "power3.out", stagger=0.004)
    js.hide(".nl-bl.fx", {"scaleY": 0, "opacity": 0})
    js.ft(".nl-bl.fx", {"scaleY": 0, "opacity": 0}, {"scaleY": 1, "opacity": 1}, steps[1], 0.26, "back.out(1.4)", stagger=0.03)
    js.hide(".nl-cap", {"scaleY": 0, "opacity": 0})
    js.ft(".nl-cap", {"scaleY": 0, "opacity": 0}, {"scaleY": 1, "opacity": 1}, steps[2], 0.18, "expo.out", stagger=0.004)
    js.hide(".nl-sfx", {"scale": 0, "opacity": 0})
    js.ft(".nl-sfx", {"scale": 0, "opacity": 0}, {"scale": 1, "opacity": 1}, steps[3], 0.24, "back.out(2.2)", stagger=0.02)
    ph0 = steps[0] + 0.06
    js.hide(f"#{pid}ph", {"opacity": 0})
    js.set(f"#{pid}ph", {"opacity": 1}, ph0)
    js.ft(f"#{pid}ph", {"x": 0}, {"x": travel}, ph0, t_fold - ph0, "power2.inOut")
    js.mblur(f"#{pid}ph", ph0, t_fold - ph0, dx=travel, ease_="power2.inOut", k=0.5)
    lo, hi = span

    def tc(p, f):
        k = 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2
        return {"textContent": _nl_tc(lo + (hi - lo) * k)}
    js.per_frame(f"#{pid}tc", ph0, t_fold, tc)
    js.set(f"#{pid}ph", {"opacity": 0}, t_fold)
    js.to(".nl-lane", {"scaleY": 0}, t_fold, 0.2, "power3.in")
    js.to(c, {"scaleY": 0.01}, t_fold + 0.12, 0.22, "power3.in")
    js.to(c, {"scaleX": 0, "opacity": 0}, t_fold + 0.34, 0.14, "power3.in")


# ---------------------------------------------------------------------------------------------- palette-fan
PF_CSS = (".rrh-palette-fan .pf-fan{position:absolute;left:0;top:0;width:1080px}"
          ".rrh-palette-fan .pf-s{position:absolute;width:250px;border-radius:24px;background:var(--h-card);"
          "box-shadow:0 14px 28px rgba(0,0,0,.14),0 2px 6px rgba(0,0,0,.08)}"
          ".rrh-palette-fan .pf-th{position:absolute;left:14px;top:14px;width:222px;height:395px;border-radius:14px;overflow:hidden;"
          "background:#000}"
          ".rrh-palette-fan .pf-th img,.rrh-palette-fan .pf-th video{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover}"
          ".rrh-palette-fan .pf-th .k-vid{position:absolute;inset:0}"
          ".rrh-palette-fan .pf-chips{position:absolute;left:14px;top:424px;display:flex;gap:10px}"
          ".rrh-palette-fan .pf-chips i{width:60px;height:60px;border-radius:10px;display:block}"
          ".rrh-palette-fan .pf-nm{position:absolute;left:125px;bottom:20px;transform-origin:0 50%;transform:rotate(-90deg);"
          "white-space:nowrap;font:700 26px/1 var(--h-fm);letter-spacing:.04em;color:var(--h-ink)}"
          ".rrh-palette-fan .pf-pin{position:absolute;width:44px;height:44px;border-radius:22px;background:var(--h-ink);"
          "border:8px solid var(--h-card)}"
          ".rrh-palette-fan .pf-lab{position:absolute;left:0;width:1080px;text-align:center;white-space:nowrap;"
          "font:900 92px/1 var(--k-fd);letter-spacing:-.025em;word-spacing:.08em;color:var(--h-ink)}"
          ".rrh-palette-fan .pf-lab span{display:inline-block;box-shadow:inset 0 -18px 0 var(--h-hl)}")


LOOKS = ["none", "saturate(1.4) contrast(1.1)", "grayscale(1) contrast(1.15)", "sepia(.4) saturate(1.2)",
         "contrast(1.25) brightness(.9)", "hue-rotate(-12deg) saturate(1.3)", "saturate(.6) brightness(1.08)"]


def _pf_chips(kit, i):
    c = kit.brand["colors"]
    base = [c["accent"], c.get("highlight", c["accent"]), c.get("alert", c["accent"]), c["ink"], c["bg"]]
    return [mix(base[(i + k) % 5], base[(i + k + 2) % 5], .7 + .1 * k) for k in range(3)]


@hero("palette-fan", "palette_fan",
      fields={"items": ("media", (3, 7)), "names": ("texts", (0, 7, 16)), "label": ("text", (22, False)),
              "pick": ("num", (0, 6)), "at": ("anchor", ()), "fan_at": ("anchor", ()), "pick_at": ("anchor", ()),
              "until": ("anchor", ()), "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)"], layouts=["split", "card", "stage"],
      say=["fan out the styles", "show the palette", "pick one from the deck"],
      what="style swatches rise as a closed paint deck and fan out on your word, each a live thumbnail with colour "
           "chips and a name along its strip; the picked one lifts out on its word while the rest dim", min_secs=2.2)
def palette_fan(self, items=None, names=None, label=None, pick=0, at=0.0, fan_at=None, pick_at=None, until=None,
                src="assets/aroll.mp4", looks=None, tone="tan", layout="split", area=None, track=None, z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    t_fan = ck.at(fan_at, 0.45, "visual", floor=t_in + 0.35)
    t_pick = ck.at(pick_at, t_fan - t_in + 1.0, "visual", floor=t_fan + 0.5)
    t_out = ck.end(until, t_pick + 0.9)
    media = list(items or [src] * 5)
    n = max(3, min(4, len(media)))
    media = media[:n]
    pick = int(pick) % n
    pid = self.uid("pf")
    js = JS(pid)
    js.split = stage.layout == "split"
    pivot = (540, stage.y1 + 10)
    sh = min(640, stage.h - 160)
    strips = []
    for i, m in enumerate(media):
        trk = track + i if track is not None else self.track(30)
        style = f"filter:{LOOKS[i % len(LOOKS)]}" if (looks if looks is not None else not items) else ""
        th = _media(m, t_in, t_out, trk, "k-vid", style) if items else _video(m, t_in, t_out, trk, 0.0, LOOKS[i % 7])
        chips = "".join(f'<i style="background:{c}"></i>' for c in _pf_chips(self, i))
        nm = (f'<span class="pf-nm" {box("glyph", t_fan, t_out, False)}>{esc(names[i])}</span>'
              if names and i < len(names) else "")
        strips.append(f'<div class="pf-s s{i}" style="left:{pivot[0] - 125}px;top:{pivot[1] - sh}px;height:{sh}px;'
                      f'transform-origin:125px {sh - 26}px;z-index:{10 + i}"><div class="pf-th">{th}</div>'
                      f'<div class="pf-chips">{chips}</div>{nm}</div>')
    pin = f'<i class="pf-pin" style="left:{pivot[0] - 22}px;top:{pivot[1] - 44}px;z-index:30"></i>'
    lab = (f'<div class="pf-lab" style="top:{stage.y0 + 6}px" {box("text", t_fan + 0.3, t_out)}><span>{esc(label)}</span></div>'
           if label else "")
    step = min(19.0, 92.0 / (n - 1))
    rots = [(i - (n - 1) / 2) * step for i in range(n)]
    _pf_js(js, n, rots, pick, t_in, t_fan, t_pick, t_out, bool(label))
    inner = f'<div class="pf-fan" {box("panel", t_in, t_out, False)} style="top:0;height:960px">{"".join(strips)}{pin}</div>{lab}'
    html = root(pid, "palette-fan", self, tone, inner + js.svg_defs(), stage, full=stage.layout != "split",
                extra_css=PF_CSS, z=z)
    ev = [sfx(t_in, "whoosh", "deck rises"), sfx(t_fan, "whoosh", "fan opens"), sfx(t_pick, "stamp", "pick lifts")]
    meta = {"times": {"in": t_in, "fan": t_fan, "pick": t_pick, "out": t_out}, "box": [90, stage.y0, 900, stage.h],
            "rotations": rots}
    return make("palette-fan", self, pid, html, js, ev, t_in, t_out + 0.25, meta)


def _pf_js(js, n, rots, pick, t_in, t_fan, t_pick, t_out, has_label):
    import math
    js.life(t_in, t_out + 0.24)
    js.ground_in(t_in, 0.4)
    js.ft(".pf-fan", {"opacity": 0, "y": 320, "scale": 0.94}, {"opacity": 1, "y": 0, "scale": 1}, t_in + 0.05, 0.5,
          "expo.out")
    js.mblur(".pf-fan", t_in + 0.05, 0.5, dy=320, ease_="expo.out", k=0.35)
    for i in range(n):
        c = i - (n - 1) / 2
        js.hide(f".s{i}", {"rotation": c * 1.5})
        if t_fan - t_in > 1.0:          # the deck eases open a little while it waits for its word
            js.to(f".s{i}", {"rotation": c * 4.0}, t_in + 0.4, max(0.4, t_fan - t_in - 0.4), "sine.inOut")
        js.to(f".s{i}", {"rotation": rots[i]}, t_fan + 0.025 * abs(c), 0.62, "back.out(1.4)")
    r = math.radians(rots[pick])
    js.to(f".s{pick}", {"x": round(math.sin(r) * 150, 1), "y": round(-math.cos(r) * 40, 1)}, t_pick - 0.16, 0.2,
          "power2.out")                    # slides out of the deck first, then rises over it
    js.set(f".s{pick}", {"zIndex": 40}, t_pick + 0.04)
    js.to(f".s{pick}", {"x": round(math.sin(r) * 60, 1), "y": round(-math.cos(r) * 45, 1), "scale": 1.05}, t_pick + 0.04,
          0.42, "back.out(1.4)")
    for i in range(n):
        if i != pick:
            js.to(f".s{i}", {"opacity": 0.85, "filter": "saturate(.6) brightness(.92)"}, t_pick, 0.3, "power2.out")
    if has_label:
        js.hide(".pf-lab", {"opacity": 0})
        js.ft(".pf-lab", {"opacity": 0, "y": 30, "scale": 0.9, "filter": "blur(10px)"},
              {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, t_fan + 0.2, 0.4, "expo.out")
    if t_out - t_pick > 1.0:
        js.ft(".pf-fan", {"scale": 1}, {"scale": 1.03}, t_pick + 0.5, t_out - t_pick - 0.5, "none")
    js.to(".pf-fan,.pf-lab", {"opacity": 0, "y": 60, "filter": "blur(8px)"}, t_out, 0.22, "power3.in")
