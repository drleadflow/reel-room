"""heroes_fire: fire-timeline. An editing-timeline card chars from its bottom edge on the ignite word, catches
procedural fire on the burn word (flame tongues keyed per frame from a seeded noise, a scrolling turbulence
displacement for the licking edge, rising embers, heat shimmer on the card, a glow on the ground), then drops away
under motion blur. Everything is SVG + GSAP keyed per frame (seek-safe, deterministic): no canvas, no randomness
outside a seeded generator. Colours are brand mixes (highlight -> alert -> ink). Reel Room's own code.
"""
import math

from heroes_base import (FPS, JS, Clock, Stage, box, colour_set, esc, hero, make, mix, prng, rgba, root, sfx)

N_FLAMES, N_EMBERS = 26, 40


def _noise(seed):
    r = prng(seed)
    ph = [r() * 6.283 for _ in range(4)]
    fr = [1.7 + r() * 1.3, 3.1 + r() * 2.0, 5.3 + r() * 2.4, 8.9 + r() * 3.0]
    return lambda t: sum(math.sin(f * t * 2.0 + p) / (k + 1) for k, (f, p) in enumerate(zip(fr, ph))) / 1.9


def _flame_path(w, h):
    """A candle-flame tongue: a full belly, a curling tip (no straight triangle edges)."""
    return (f"M{-w / 2:.1f} 0 C{-w * .56:.1f} {-h * .3:.1f} {-w * .3:.1f} {-h * .52:.1f} {-w * .08:.1f} {-h * .76:.1f} "
            f"C{w * .02:.1f} {-h * .88:.1f} {-w * .06:.1f} {-h * .95:.1f} {w * .04:.1f} {-h:.1f} "
            f"C{w * .1:.1f} {-h * .8:.1f} {w * .34:.1f} {-h * .62:.1f} {w * .44:.1f} {-h * .36:.1f} "
            f"C{w * .52:.1f} {-h * .18:.1f} {w * .5:.1f} {-h * .06:.1f} {w / 2:.1f} 0 Z")


def _char_path(cw, ch, seed=4):
    r = prng(seed)
    pts = [(x, 18 * math.sin(x / 47.0 + 1.3) + 10 * (r() - .5)) for x in range(-20, cw + 41, 20)]
    top = " L".join(f"{x:.0f} {y:.1f}" for x, y in pts)
    return f"M{-20} {ch + 40} L{top} L{cw + 40} {ch + 40} Z", " L".join(f"{x:.0f} {y:.1f}" for x, y in pts)


def _card(pal, title, cw, ch, t_in, t_burn):
    tracks = [(0.06, 0.34, 0), (0.36, 0.52, 1), (0.55, 0.98, 0), (0.06, 0.46, 2), (0.48, 0.62, 1), (0.64, 0.98, 2),
              (0.06, 0.98, 3)]
    tones = [pal["clip"], pal["hl"], pal["acc"], pal["clip2"]]
    blocks = "".join(f'<i class="ft-b" style="left:{110 + a * (cw - 140):.0f}px;top:{120 + [0, 0, 0, 1, 1, 1, 2][k] * 92:.0f}px;'
                     f'width:{(b - a) * (cw - 140) - 8:.0f}px;background:{tones[c]}"></i>' for k, (a, b, c) in enumerate(tracks))
    labs = "".join(f'<span class="ft-l" style="top:{137 + i * 92}px">{n}</span>' for i, n in enumerate(("V2", "V1", "A1")))
    ttl = (f'<span class="ft-t" {box("text", t_in + 0.2, t_burn)}>{esc(title)}</span>' if title else "")
    return (f'<div class="ft-head"><i style="background:{pal["alert"]}"></i><i style="background:{pal["hl"]}"></i>'
            f'<i style="background:{pal["acc"]}"></i>{ttl}</div>{labs}{blocks}<i class="ft-ph"></i>')


def _pal(kit):
    c = kit.brand["colors"]
    hl, al, ink = c.get("highlight", c["accent"]), c.get("alert", c["accent"]), c["ink"]
    return {"card": mix(ink, c["bg"], .86), "ink": c["bg"], "clip": mix(c["bg"], ink, .74), "clip2": mix(c["bg"], ink, .5),
            "hl": hl, "acc": mix(c["accent"], "#ffffff", .8), "alert": al, "f1": mix(hl, "#ffffff", .7),
            "f2": hl, "f3": mix(hl, al, .45), "f4": al, "char": mix(ink, "#000000", .9), "rim": mix(hl, al, .6)}


CSS = (".rrh-fire-timeline .ft-wrap{position:absolute;transform-origin:50% 100%}"
       ".rrh-fire-timeline .ft-card{position:absolute;left:0;top:0;border-radius:30px;overflow:hidden;box-shadow:var(--h-shadow)}"
       ".rrh-fire-timeline .ft-head{position:absolute;left:30px;top:26px;display:flex;align-items:center;gap:12px;white-space:nowrap}"
       ".rrh-fire-timeline .ft-head i{width:18px;height:18px;border-radius:9px;display:block}"
       ".rrh-fire-timeline .ft-t{margin-left:14px;font:800 48px/1 var(--k-fd);letter-spacing:-.01em;color:var(--h-ink)}"
       ".rrh-fire-timeline .ft-l{position:absolute;left:28px;font:800 32px/38px var(--h-fm);color:var(--h-ink)}"
       ".rrh-fire-timeline .ft-b{position:absolute;height:64px;border-radius:10px;display:block}"
       ".rrh-fire-timeline .ft-ph{position:absolute;left:300px;top:100px;width:5px;height:300px;border-radius:3px;"
       "background:var(--h-alert);display:block}"
       ".rrh-fire-timeline svg.ft-fx{position:absolute;left:0;top:0;overflow:visible}"
       ".rrh-fire-timeline .ft-glow{position:absolute;left:-200px;width:1480px;height:900px;border-radius:50%}")


@hero("fire-timeline", "fire_timeline",
      fields={"title": ("text", (24, False)), "at": ("anchor", ()), "ignite": ("anchor", ()), "burn": ("anchor", ()),
              "until": ("anchor", ()), "tone": ("set", ())},
      fits=["split-deck (top slot)", "motion-editorial (stage)", "full-frame styles (band above the head)"],
      layouts=["split", "card", "stage", "full", "overlay"],
      say=["set the timeline on fire", "burn it", "it's cooked"],
      what="an editing-timeline card chars from the bottom on one word and catches real-looking fire on the next "
           "(licking flames, embers, heat shimmer), then drops away", min_secs=2.0)
def fire_timeline(self, title=None, at=0.0, ignite=None, burn=None, until=None, tone="dark", layout="split", area=None,
                  z=None):
    stage = Stage(layout, area)
    ck = Clock(self, at)
    t_in = ck.t_in
    t_ig = ck.at(ignite, 0.6, "visual", floor=t_in + 0.45)
    t_burn = ck.at(burn, t_ig - t_in + 0.6, "stamp", floor=t_ig + 0.3)
    t_out = ck.end(until, t_burn + 1.0, hold=0.4)
    t_drop = max(t_burn + 0.8, t_out - 0.4)
    pal = _pal(self)
    cw, ch = 960, 470
    x, y, w, h = stage.fit(cw, ch, valign=0.62)
    pid = self.uid("ft")
    js = JS(pid)
    js.split = stage.layout == "split"
    char_d, rim_d = _char_path(cw, ch)
    flames, embers = _fire_svg(pid, pal, cw, ch)
    fx = (f'<svg class="ft-fx" width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">{_defs(pid, pal, cw, ch)}'
          f'<g clip-path="url(#{pid}cl)"><g class="ft-char"><path d="{char_d}" fill="{pal["char"]}" opacity=".93"/>'
          f'<path d="M{rim_d}" fill="none" stroke="{pal["rim"]}" stroke-width="7" filter="url(#{pid}gl)"/></g></g>'
          f'<g class="ft-fl">{flames}</g>{embers}</svg>')
    glow = (f'<div class="ft-glow" style="top:{y + ch - 380}px;background:radial-gradient(closest-side,{rgba(pal["f3"], .55)},'
            f'{rgba(pal["f4"], .18)} 55%,transparent 100%)"></div>')
    inner = (glow + f'<div class="ft-wrap" style="left:{x}px;top:{y}px;width:{cw}px;height:{ch}px">'
             f'<div class="ft-card" style="width:{cw}px;height:{ch}px;background:{pal["card"]}" {box("card", t_in, t_drop, False)}>'
             f'{_card(pal, title, cw, ch, t_in, t_burn)}</div>{fx}</div>')
    _fire_js(js, pid, cw, ch, t_in, t_ig, t_burn, t_drop, t_out)
    html = root(pid, "fire-timeline", self, tone, inner + js.svg_defs(), stage, full=stage.layout != "split",
                extra_css=CSS, z=z)
    ev = [sfx(t_in, "whoosh", "timeline card"), sfx(t_ig, "click", "scorch", "full"), sfx(t_burn, "impact", "catches fire"),
          sfx(t_drop, "whoosh", "drops away")]
    meta = {"times": {"in": t_in, "ignite": t_ig, "burn": t_burn, "drop": t_drop, "out": t_out}, "box": [x, y, cw, ch]}
    return make("fire-timeline", self, pid, html, js, ev, t_in, t_out, meta)


def _defs(pid, pal, cw, ch):
    return (f'<defs><clipPath id="{pid}cl"><rect width="{cw}" height="{ch}" rx="30"/></clipPath>'
            f'<linearGradient id="{pid}fg" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{pal["f1"]}"/>'
            f'<stop offset=".25" stop-color="{pal["f2"]}"/><stop offset=".6" stop-color="{pal["f3"]}"/>'
            f'<stop offset=".88" stop-color="{pal["f4"]}" stop-opacity=".75"/><stop offset="1" stop-color="{pal["f4"]}" '
            f'stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="{pid}fo" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{pal["f2"]}"/>'
            f'<stop offset=".35" stop-color="{pal["f3"]}"/><stop offset=".75" stop-color="{pal["f4"]}" stop-opacity=".8"/>'
            f'<stop offset="1" stop-color="{pal["f4"]}" stop-opacity="0"/></linearGradient>'
            f'<radialGradient id="{pid}eg"><stop offset="0" stop-color="{pal["f1"]}"/><stop offset=".5" stop-color="{pal["f2"]}"/>'
            f'<stop offset="1" stop-color="{pal["f4"]}" stop-opacity="0"/></radialGradient>'
            f'<filter id="{pid}gl" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>'
            f'<filter id="{pid}dp" x="-20%" y="-60%" width="140%" height="180%"><feTurbulence type="fractalNoise" '
            f'baseFrequency="0.009 0.032" numOctaves="3" seed="3" result="n"/><feOffset id="{pid}off" in="n" dx="0" dy="0" '
            f'result="m"/><feDisplacementMap in="SourceGraphic" in2="m" scale="62" xChannelSelector="R" '
            f'yChannelSelector="G" result="d"/><feGaussianBlur in="d" stdDeviation="9"/></filter>'
            f'<filter id="{pid}dc" x="-20%" y="-60%" width="140%" height="180%"><feTurbulence type="fractalNoise" '
            f'baseFrequency="0.02 0.07" numOctaves="2" seed="9" result="n"/><feOffset id="{pid}off2" in="n" dx="0" dy="0" '
            f'result="m"/><feDisplacementMap in="SourceGraphic" in2="m" scale="18" xChannelSelector="R" '
            f'yChannelSelector="G" result="d"/><feGaussianBlur in="d" stdDeviation="2"/></filter>'
            f'<filter id="{pid}heat" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" '
            f'baseFrequency="0.02 0.06" numOctaves="1" seed="8" result="n"/><feOffset id="{pid}hoff" in="n" dx="0" dy="0" '
            f'result="m"/><feDisplacementMap in="SourceGraphic" in2="m" scale="0" id="{pid}hdm" xChannelSelector="R" '
            f'yChannelSelector="G"/></filter></defs>')


def _fire_svg(pid, pal, cw, ch):
    """Flame tongues in two layers: soft outer bodies (orange -> red, wide, heavily blurred and licked by the
    turbulence) and hot cores (white-yellow, narrow, a lighter blur), so the fire reads as light, not shapes."""
    r = prng(21)
    outer, core = [], []
    for i in range(N_FLAMES):
        fxp = 20 + (cw - 40) * (i + .5) / N_FLAMES + (r() - .5) * 34
        fw, fh = 95 + r() * 75, 170 + r() * 230
        tr = f'transform="translate({fxp:.0f} {ch + 10})"'
        outer.append(f'<path class="ft-f f{i}" {tr} d="{_flame_path(fw, fh)}" fill="url(#{pid}fo)" opacity=".85"/>')
        core.append(f'<path class="ft-f f{i}" {tr} d="{_flame_path(fw * .46, fh * .58)}" fill="url(#{pid}fg)"/>')
    em = []
    for i in range(N_EMBERS):
        em.append(f'<circle class="ft-e e{i}" cx="{40 + r() * (cw - 80):.0f}" cy="{ch * .55 + r() * ch * .4:.0f}" '
                  f'r="{2.5 + r() * 4:.1f}" fill="url(#{pid}eg)"/>')
    fl = (f'<g filter="url(#{pid}dp)" style="mix-blend-mode:screen">{"".join(outer)}</g>'
          f'<g filter="url(#{pid}dc)" style="mix-blend-mode:screen">{"".join(core)}</g>')
    return fl, "".join(em)


def _level(t, t_ig, t_burn, t_drop):
    """Fire size 0..1.25 over time: a scorch after ignite, a surge on burn, settles, shrinks as it drops."""
    if t < t_ig:
        return 0.0
    if t < t_burn:
        return 0.05 + 0.17 * (t - t_ig) / max(0.1, t_burn - t_ig)
    if t < t_burn + 0.25:
        return 0.22 + 1.03 * math.sin(min(1.0, (t - t_burn) / 0.25) * math.pi / 2)
    return max(0.0, 1.25 - 0.25 * min(1.0, (t - t_burn - 0.25) / 0.4) - (0.9 if t > t_drop + 0.25 else 0))


def _fire_js(js, pid, cw, ch, t_in, t_ig, t_burn, t_drop, t_out):
    js.life(t_in, t_out)
    js.ground_in(t_in, 0.4)
    js.ft(".ft-wrap", {"opacity": 0, "y": 60, "scale": 0.94, "filter": "blur(12px)"},
          {"opacity": 1, "y": 0, "scale": 1, "filter": "blur(0px)"}, t_in + 0.05, 0.44, "back.out(1.4)")
    js.ft(".ft-ph", {"x": 0}, {"x": 520}, t_in + 0.1, max(0.4, t_burn - t_in), "sine.inOut")
    js.ft(".ft-card", {"scale": 1}, {"scale": 1.025}, t_in + 0.5, max(0.4, t_drop - t_in - 0.5), "none")
    js.hide(".ft-char", {"y": ch + 30})
    js.to(".ft-char", {"y": ch * 0.72}, t_ig, max(0.2, t_burn - t_ig), "sine.inOut")
    js.to(".ft-char", {"y": ch * 0.3}, t_burn, max(0.3, t_drop - t_burn), "power2.out")
    js.hide(".ft-glow", {"opacity": 0})
    js.to(".ft-glow", {"opacity": 0.45}, t_ig, max(0.2, t_burn - t_ig), "power2.out")
    js.to(".ft-glow", {"opacity": 1}, t_burn, 0.25, "power2.out")
    js.to(".ft-glow", {"opacity": 0}, t_drop, 0.35, "power3.in")
    js.hide(".ft-f", {"scaleY": 0, "scaleX": 0.6, "transformOrigin": "50% 100%"})
    noise = [_noise(40 + i) for i in range(N_FLAMES)]
    f0, f1 = int(round(t_ig * FPS)), int(round((t_drop + 0.4) * FPS))
    for f in range(f0, f1 + 1):
        t = f / FPS
        lv = _level(t, t_ig, t_burn, t_drop)
        front = _front(t, ch, t_ig, t_burn, t_drop)
        for i in range(N_FLAMES):
            n = noise[i](t)
            js.set(f".f{i}", {"scaleY": round(max(0.0, lv * (0.85 + 0.32 * n)), 3), "scaleX": round(0.75 + 0.2 * n, 3),
                              "skewX": round(15 * noise[(i + 3) % N_FLAMES](t * 1.3), 2), "y": round(front, 1)}, t)
        js.set(f"#{pid}off", {"attr": {"dy": round(-140 * t % 4000, 1)}}, t)
        js.set(f"#{pid}off2", {"attr": {"dy": round(-210 * t % 4000, 1)}}, t)
    js.set(".ft-card", {"filter": f"url(#{pid}heat)"}, t_burn)
    js.to(f"#{pid}hdm", {"attr": {"scale": 9}}, t_burn, 0.4, "power2.out")
    js.per_frame(f"#{pid}hoff", t_burn, t_drop + 0.4, lambda p, f: {"attr": {"dy": round(-90 * f / FPS % 3000, 1)}})
    r = prng(77)
    for i in range(N_EMBERS):
        te = t_burn - 0.05 + r() * (t_drop - t_burn + 0.2)
        js.hide(f".e{i}", {"opacity": 0})
        js.ft(f".e{i}", {"opacity": 0, "scale": 0.3}, {"opacity": 1, "scale": 1}, te, 0.1, "power2.out")
        js.to(f".e{i}", {"y": -(220 + r() * 320), "x": (r() - .5) * 140}, te, 0.9 + r() * 0.5, "power2.out")
        js.to(f".e{i}", {"opacity": 0}, te + 0.5, 0.45, "power2.in")
    js.to(".ft-wrap", {"y": 1100, "rotation": 9}, t_drop, 0.46, "power2.in")
    js.mblur(".ft-wrap", t_drop, 0.46, dy=1100, ease_="power2.in", k=0.28)


def _front(t, ch, t_ig, t_burn, t_drop):
    """y of the burn front inside the card (mirrors the .ft-char tweens) so the flames ride it."""
    def sio(p):
        return -(math.cos(math.pi * min(1.0, max(0.0, p))) - 1) / 2
    if t <= t_ig:
        return ch + 30
    if t <= t_burn:
        return ch + 30 + (ch * 0.72 - ch - 30) * sio((t - t_ig) / max(0.2, t_burn - t_ig))
    p = min(1.0, (t - t_burn) / max(0.3, t_drop - t_burn))
    return ch * 0.72 + (ch * 0.3 - ch * 0.72) * (1 - (1 - p) ** 3)
