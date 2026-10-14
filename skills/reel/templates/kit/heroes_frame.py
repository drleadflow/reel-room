"""heroes_frame: whole-frame heroes. grid-collapse (the frame shrinks into the centre tile of a 3x3 grid, eight tiles
pop in from the centre out, then fall away and the speaker snaps back full frame) and reel-orbit (the creator's own
reels orbit the speaker in depth: front copies over the speaker, back copies under the cut-out, or fading behind the
head when there is no matte).

grid-collapse's geometry and beat order (centre tile starts as the identity of the full frame, backdrop a frame late,
sides then corners pop, seeded tilt and gravity fall, snap back) are adapted from reel-kit fx/grid-collapse,
Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md at the repository root). reel-orbit is a
clean-room Reel Room build from a generic idea (tiles on an ellipse, depth scale, front/back layering); no code or text
from any unlicensed source was used.
"""
import math

from comps_fx import _video
from heroes_base import (FPS, JS, Clock, Stage, box, colour_set, esc, hero, make, prng, root, sfx)
from heroes_edit import IMG_EXT

G_GAP = 14
TW = (1080 - 4 * G_GAP) / 3
K = TW / 1080
TH = 1920 * K
Y0 = (1920 - (3 * TH + 2 * G_GAP)) / 2
RING = [(0, 1), (1, 0), (1, 2), (2, 1)]
CORNERS = [(0, 0), (0, 2), (2, 2), (2, 0)]
LOOKS = ["saturate(1.35) contrast(1.08)", "grayscale(1) contrast(1.2)", "sepia(.45) saturate(1.15)",
         "hue-rotate(-14deg) saturate(1.3)", "contrast(1.3) brightness(.88)", "saturate(.55) brightness(1.1)",
         "sepia(.2) contrast(1.15) saturate(1.25)", "grayscale(.6) brightness(1.05)"]


def _tx(c):
    return G_GAP + c * (TW + G_GAP)


def _ty(r):
    return Y0 + r * (TH + G_GAP)


def _tile_media(src, i, t0, t1, track):
    if src and str(src).lower().endswith(IMG_EXT):
        return f'<img src="{esc(src)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">'
    v = _video(src or "assets/aroll.mp4", t0, t1, track, 0.0, LOOKS[i % len(LOOKS)], cls="gc-v")
    return v


def _zblur(js, sel, t, dur, peak=10.0):
    """Blur that rises and falls across a fast zoom (a zoom has no single direction): keyed per frame."""
    n = max(2, int(round(dur * FPS)))
    for i in range(n + 1):
        b = peak * math.sin(math.pi * i / n)
        js.set(sel, {"filter": f"blur({b:.1f}px)" if b > 0.6 else "none"}, t + i / FPS)


@hero("grid-collapse", "grid_collapse",
      fields={"at": ("anchor", ()), "pop_at": ("anchor", ()), "cue": ("anchor", ()), "until": ("anchor", ()),
              "tiles": ("media", (0, 8))},
      fits=["split-deck (full-frame beat)", "any full-frame style"], layouts=["full", "overlay"], split_mode="full",
      say=["shrink me into a grid", "you are one of many", "lots of people do this"],
      what="the frame shrinks into the centre tile of a 3x3 grid, eight tiles (your own clips or stills) pop in from "
           "the centre out, then on the word they fall away and you snap back full frame", min_secs=1.6)
def grid_collapse(self, at=0.0, pop_at=None, cue=None, until=None, tiles=None, src="assets/aroll.mp4", tone="dark",
                  layout="full", area=None, track=None, z=None):
    ck = Clock(self, at, "push")
    t_in = ck.t_in
    t_pop = ck.at(pop_at, 0.12, "visual", floor=t_in + 0.06)
    t_cue = ck.at(cue, t_pop - t_in + 0.9, "visual", floor=t_pop + 0.55)
    t_out = max(t_cue + 0.75, ck.end(until, t_cue + 0.4, hold=0.0))
    pid = self.uid("gc")
    js = JS(pid)
    trk = track if track is not None else self.track(30)
    tiles = list(tiles or [])
    outer = RING + CORNERS
    cells = []
    for i, (r, c) in enumerate(outer):
        m = tiles[i] if i < len(tiles) else None
        cells.append(f'<div class="gc-t t{r}{c}" style="left:{_tx(c):.2f}px;top:{_ty(r):.2f}px" '
                     f'{box("image", t_pop, t_cue, False)}>{_tile_media(m or src, i, t_in, t_out, trk + 1 + i)}</div>')
    centre = (f'<div class="gc-t t11" style="left:{_tx(1):.2f}px;top:{_ty(1):.2f}px">'
              f'<div class="gc-c">{_video(src, t_in, t_out, trk, 0.0, cls="gc-v")}</div></div>')
    bg = colour_set(self, tone)["g"]
    css = (f".rrh-grid-collapse .gc-bg{{position:absolute;left:0;top:0;width:1080px;height:1920px;background:{bg}}}"
           f".rrh-grid-collapse .gc-t{{position:absolute;width:{TW:.2f}px;height:{TH:.2f}px;overflow:hidden;border-radius:26px;"
           f"background:#000;box-shadow:0 18px 40px rgba(0,0,0,.4),inset 0 0 0 3px rgba(255,255,255,.18)}}.rrh-grid-collapse .gc-v{{position:absolute;left:0;top:0;width:1080px;height:1920px;"
           f"transform-origin:0 0;transform:scale({K:.6f})}}.rrh-grid-collapse .gc-v video{{position:absolute;left:0;top:0;"
           f"width:1080px;height:1920px;object-fit:cover}}.rrh-grid-collapse .gc-c{{position:absolute;inset:0}}"
           f".rrh-grid-collapse .t11{{z-index:5}}")
    inner = f'<div class="gc-bg"></div>{"".join(cells)}{centre}'
    _gc_js(js, t_in, t_pop, t_cue, t_out, outer)
    html = root(pid, "grid-collapse", self, tone, inner + js.svg_defs(), Stage("full", area), full=True,
                extra_css=css, z=z)
    ev = [sfx(t_in, "whoosh", "frame shrinks"), sfx(t_pop, "pop", "tiles pop"), sfx(t_cue, "whoosh", "tiles fall")]
    ev += [sfx(t_pop + 0.033 * i, "pop", f"tile {i}", "full") for i in range(1, 8)]
    meta = {"times": {"in": t_in, "pop": t_pop, "cue": t_cue, "out": t_out}, "box": [0, 0, 1080, 1920],
            "track": trk}
    return make("grid-collapse", self, pid, html, js, ev, t_in, t_out, meta)


def _gc_js(js, t_in, t_pop, t_cue, t_out, outer):
    js.life(t_in, t_out)
    js.hide(".gc-bg", {"opacity": 0})
    js.set(".gc-bg", {"opacity": 1}, t_in + 1 / FPS)
    full = {"x": -_tx(1), "y": -_ty(1), "scale": 1 / K, "borderRadius": 0, "transformOrigin": "0 0"}
    js.hide(".t11", full)
    js.ft(".t11", {k: v for k, v in full.items() if k != "transformOrigin"}, {"x": 0, "y": 0, "scale": 1, "borderRadius": 26},
          t_in, 0.34, "power3.inOut")
    _zblur(js, ".t11 .gc-c", t_in + 0.04, 0.26, 3.5)
    r = prng(9)
    for i, (rr, cc) in enumerate(outer):
        sel = f".t{rr}{cc}"
        t = t_pop + (i * 0.033 if i < 4 else 0.13 + (i - 4) * 0.033)
        js.hide(sel, {"opacity": 0, "transformOrigin": "50% 50%"})
        js.ft(sel, {"opacity": 0, "scale": 0.45, "filter": "blur(6px)"}, {"opacity": 1, "scale": 1, "filter": "blur(0px)"},
              t, 0.3, "back.out(1.4)")
        dc, dr = cc - 1, rr - 1
        tf = t_cue + r() * 0.03
        fall = 900 + r() * 260
        js.to(sel, {"scale": 0.62}, tf, 0.22, "power3.out")
        js.to(sel, {"x": dc * 200, "y": dr * 220 + fall, "rotation": round((dc or (r() - .5) * 2) * (8 + r() * 8), 1)},
              tf, 0.42, "power2.in")
        js.mblur(sel, tf, 0.42, dy=fall, dx=dc * 200, ease_="power2.in", k=0.3)
    js.to(".t11", {"x": -_tx(1), "y": -_ty(1), "scale": 1 / K, "borderRadius": 0}, t_cue, 0.32, "power3.inOut")
    js.set(".gc-bg", {"opacity": 0}, t_cue + 0.2)


# ---------------------------------------------------------------------------------------------- reel-orbit
RO_W, RO_H = 250, 444


def _ro_angle(t, t0, spin, tau=0.5):
    """Orbit angle: spins up from rest (no linear crawl on the first frame), then cruises at 2*pi/spin."""
    w = 2 * math.pi / spin
    d = max(0.0, t - t0)
    return w * (d - tau * (1 - math.exp(-d / tau)))


def _ro_rows(n, t_in, t_out, spin, centre, rx, ry, face, matte):
    """Per-frame {x, y, scale, zIndex, opacity, filter} for every tile."""
    cx, cy = centre
    fx, fy, fh = face
    f0, f1 = int(round(t_in * FPS)), int(round(t_out * FPS))
    rows = [[] for _ in range(n)]
    for f in range(f0, f1 + 1):
        t = f / FPS
        grow = 1 - (1 - min(1.0, (t - t_in) / 0.6)) ** 4
        leave_t = max(0.0, (t - (t_out - 0.55)) / 0.55)
        for i in range(n):
            leave = max(0.0, min(1.0, (leave_t * 0.55 - 0.04 * i) / 0.4)) ** 2      # staggered, eased fly-out
            th = 2 * math.pi * i / n + _ro_angle(t, t_in, spin) - math.pi / 2
            depth = math.sin(th)
            rad = 0.15 + 0.85 * grow + 1.4 * leave
            x, y = cx + rx * rad * math.cos(th), cy + ry * rad * depth
            s = (0.6 + 0.4 * (depth + 1) / 2) * (0.3 + 0.7 * grow)
            op = 1.0 - leave
            if depth < 0 and not matte:
                near = abs(x - fx) / (fh * 1.15 + RO_W * s / 2)
                op *= min(1.0, max(0.0, (near - 0.55) / 0.45))
            speed = rx * rad * 2 * math.pi / spin / FPS + 1400 * leave / FPS
            blur = min(8.0, speed * 0.18) if leave > 0 or grow < 1 else 0.0
            blur = max(blur, 2.5 * max(0.0, -depth))           # depth of field: the back of the orbit softens
            rows[i].append((t, {"x": round(x - RO_W / 2, 1), "y": round(y - RO_H / 2, 1), "scale": round(s, 3),
                                "rotationY": round(-math.cos(th) * 42, 1), "transformPerspective": 900,
                                "zIndex": (60 if depth >= 0 else 10) + int(10 * depth), "opacity": round(op, 3),
                                "filter": f"blur({blur:.1f}px)" if blur > 0.6 else "none"}))
    return rows


@hero("reel-orbit", "reel_orbit",
      fields={"media": ("media", (4, 8)), "at": ("anchor", ()), "until": ("anchor", ()), "spin": ("secs", (2.5, 9))},
      fits=["split-deck (full-frame beat)", "any full-frame style; best with a cut-out"], layouts=["full", "overlay"],
      split_mode="full", say=["orbit my reels around me", "my reels spin around me", "show my other videos around me"],
      what="your own reels (thumbnails from your project or folder) orbit you in depth: front copies pass over you, "
           "back copies go behind your head (under the cut-out, or fading out without one), then fly out",
      min_secs=1.8)
def reel_orbit(self, media, at=0.0, until=None, spin=5.2, face=(540, 900, 200), matte=None, matte_start=0.0,
               layout="full", area=None, tone="dark", track=None, z=None):
    if not media or len(media) < 3:
        raise ValueError("reel_orbit: needs 3+ of the creator's own reel thumbnails (images)")
    ck = Clock(self, at, "push")
    t_in = ck.t_in
    t_out = ck.end(until, t_in + 1.6, hold=0.6)
    fx, fy, fh = face
    centre = (fx, min(1200, fy + 1.2 * fh))
    rx, ry = 380, 220
    pid = self.uid("ro")
    js = JS(pid)
    n = min(6, len(media))
    tiles = "".join(f'<div class="ro-t r{i}" {box("image", t_in + 0.3, t_out - 0.3, False)}>'
                    f'<img src="{esc(m)}" alt=""></div>' for i, m in enumerate(media[:n]))
    matte_html = ""
    if matte:
        trk = track if track is not None else self.track(30)
        matte_html = f'<div class="ro-m">{_video(matte, t_in, t_out + 0.1, trk, -matte_start, cls="ro-mv")}</div>'
    css = (f".rrh-reel-orbit{{perspective:1600px}}.rrh-reel-orbit .ro-t{{position:absolute;left:0;top:0;width:{RO_W}px;height:{RO_H}px;border-radius:20px;"
           f"overflow:hidden;border:5px solid rgba(255,255,255,.92);box-shadow:0 18px 40px rgba(0,0,0,.35);"
           f"transform-origin:50% 50%}}.rrh-reel-orbit .ro-t img{{width:100%;height:100%;object-fit:cover;display:block}}"
           f".rrh-reel-orbit .ro-m{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:50}}"
           f".rrh-reel-orbit .ro-mv,.rrh-reel-orbit .ro-mv video{{position:absolute;left:0;top:0;width:1080px;height:1920px;"
           f"object-fit:cover}}")
    js.life(t_in, t_out)
    for i, rows in enumerate(_ro_rows(n, t_in, t_out, spin, centre, rx, ry, face, bool(matte))):
        js.hide(f".r{i}", rows[0][1])
        prev = None
        for t, v in rows:
            if v != prev:
                js.set(f".r{i}", v, t)
            prev = v
    html = root(pid, "reel-orbit", self, tone, tiles + matte_html, Stage("full", area), full=True, extra_css=css, z=z)
    ev = [sfx(t_in, "whoosh", "reels spin out"), sfx(t_in + 0.25, "pop", "tiles land", "full"),
          sfx(t_out - 0.38, "whoosh", "reels fly out")]
    meta = {"times": {"in": t_in, "out": t_out}, "box": [centre[0] - rx - RO_W / 2, centre[1] - ry - RO_H / 2,
                                                         2 * rx + RO_W, 2 * ry + RO_H], "mode": "matte" if matte else "fade"}
    return make("reel-orbit", self, pid, html, js, ev, t_in, t_out, meta)
