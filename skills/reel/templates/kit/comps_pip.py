"""Kit component, picture-in-picture family: head_bubble ("put my head in a bubble", "picture in picture me").

The speaker shrinks from the plate into a circle in a top corner while a full-screen graphic plays behind, then grows
back into the plate on `back`. Same approach as phone-frame: a frame-synced copy of the plate (`src`) lives inside the
piece, so the host's camera and layout are never touched. The copy starts and ends exactly as the plate looks on
screen (`plate` transform, `clip` region, optional `vignette`), so the hand-off is invisible both ways.

Every frame is keyed from Python (seek-safe, deterministic): the mask radius tightens on a damped spring, the circle
travels to its corner on the camera ease, the ring and the drop shadow fade in once it lands. The circle follows the
tracked face, so the face stays centred.

Rule: one shot. A cut or a whole-frame transition inside [at, back + out] breaks the hand-off (the copy shows the
plate's picture, not the host's camera move on that cut). The split engine checks this and warns.
"""
import math

from rrkit_base import W, H, FPS, box, esc, sfx
from comps_fx import _video

SPOT_X, SPOT_Y = 60, 250          # top-corner spot (safe zone: 220 px top, 35 px sides, plus a margin)
IN_DUR, OUT_DUR = 0.66, 0.56
SPRING = (11.0, 0.72)             # omega (rad/s), damping ratio: ~4 % overshoot, settled in ~0.5 s


def _spring(t, omega=SPRING[0], zeta=SPRING[1]):
    """Damped spring step response, 0 at t<=0 -> 1 (small overshoot), t in seconds."""
    if t <= 0:
        return 0.0
    wd = omega * math.sqrt(1 - zeta * zeta)
    e = math.exp(-zeta * omega * t)
    return 1 - e * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta * zeta) * math.sin(wd * t))


def _inout(p):
    """Cubic in-out (the camera intent): starts and lands softly."""
    p = min(1.0, max(0.0, p))
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def _face_at(face, t):
    """face: (x, y, h) or [(t, x, y, h), ...] (screen px, sorted) -> (x, y, h) at t, linearly interpolated."""
    if not isinstance(face[0], (list, tuple)):
        return tuple(float(v) for v in face[:3])
    rows = face
    if t <= rows[0][0]:
        return tuple(float(v) for v in rows[0][1:4])
    for a, b in zip(rows, rows[1:]):
        if a[0] <= t <= b[0]:
            k = (t - a[0]) / max(1e-6, b[0] - a[0])
            return tuple(float(a[i] + (b[i] - a[i]) * k) for i in (1, 2, 3))
    return tuple(float(v) for v in rows[-1][1:4])


def _smooth(face, t0, t1, win=0.4):
    """Per-frame face centre over [t0, t1] smoothed with a moving average (no jitter from the detector)."""
    f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
    raw = [_face_at(face, f / FPS) for f in range(f0, f1 + 1)]
    n = max(1, int(win * FPS / 2))
    out = []
    for i in range(len(raw)):
        seg = raw[max(0, i - n): i + n + 1]
        out.append(tuple(sum(r[j] for r in seg) / len(seg) for j in range(3)))
    return out


def _corner(corner, size, x=None, y=None):
    if corner not in ("tl", "tr"):
        raise ValueError(f"head_bubble: corner must be 'tl' or 'tr', got {corner!r}")
    cx = SPOT_X + size / 2 if corner == "tl" else W - SPOT_X - size / 2
    return (float(x) if x is not None else cx), (float(y) if y is not None else SPOT_Y + size / 2)


def _cover_r(px, py, region):
    """Radius from (px, py) that covers the whole plate region (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = region
    return max(math.hypot(px - cx, py - cy) for cx in (x0, x1) for cy in (y0, y1)) + 4


def _rows(t_in, t_back, t_end, face_fr, corner_xy, size, fit, region):
    """Per-frame [frame, s, tx, ty, mx, my, r, a]: the move layer is translate(tx, ty) scale(s) (origin 0 0); the mask
    circle sits at (mx, my) radius r in plate (pre-move) space; a = ring/shadow alpha."""
    f_in = int(round(t_in * FPS))
    cxc, cyc = corner_xy
    rows, prev = [], None
    for i, (fx, fy, fh) in enumerate(face_fr):
        f = f_in + i
        t = f / FPS
        r_fin = max(20.0, fit * fh)             # a missing face height never divides by zero
        k = (size / 2) / r_fin
        R0 = _cover_r(fx, fy, region)
        if t < t_back:                                   # in, then the hold
            pr = _spring(t - t_in)
            q = _inout((t - t_in - 0.06) / (IN_DUR - 0.06))
            a = min(1.0, max(0.0, (q - 0.55) / 0.45))
        else:                                            # out: travel home, then open back into the plate
            u = (t - t_back) / OUT_DUR
            q = 1 - _inout(u / 0.92)
            pr = 1 - _inout((u - 0.12) / 0.88)
            a = max(0.0, 1 - u / 0.25)
        r = R0 + (r_fin - R0) * pr
        s = 1 + (k - 1) * q
        px, py = fx + (cxc - fx) * q, fy + (cyc - fy) * q
        row = [f, round(s, 4), round(px - s * fx, 2), round(py - s * fy, 2), round(fx, 1), round(fy, 1),
               round(max(1.0, r), 1), round(a, 3)]
        if t >= t_end - 0.5 / FPS:                      # the last frame is the plate exactly
            row = [f, 1.0, 0.0, 0.0, round(fx, 1), round(fy, 1), round(R0, 1), 0.0]
        if prev is None or row[1:] != prev[1:]:
            rows.append(row)
        prev = row
    return rows


def _region(clip):
    """clip: (x0, y0, x1, y1) screen region of the plate, or None (full frame) -> (region tuple, css clip-path)."""
    if clip is None:
        return (0.0, 0.0, float(W), float(H)), "none"
    x0, y0, x1, y1 = (float(v) for v in clip)
    return (x0, y0, x1, y1), f"inset({y0:.0f}px {W - x1:.0f}px {H - y1:.0f}px {x0:.0f}px)"


def _behind(spec, t_in, t_end, track):
    """track: its own track index (never the plate copy's)."""
    if not spec:
        return ""
    s = str(spec)
    if s.lstrip().startswith("<"):
        return s                                          # host html (a diagram), drawn by the host's own tweens
    if s.endswith((".mp4", ".mov", ".webm")):
        return _video(s, t_in, t_end, track, 0.0, cls="hb-media")
    return f'<div class="hb-media" style="background-image:url(\'{esc(s)}\')"></div>'


def head_bubble(self, at=0.0, back=None, src="assets/aroll.mp4", corner="tl", size=300, ring=True, label=None,
                until=None, face=(540, 900, 190), fit=1.18, plate=None, clip=None, behind=None, ground=True,
                vignette=0.0, media_offset=0.0, x=None, y=None, track=None, z=None):
    """The speaker shrinks from the plate into a circle in a top corner (`corner` 'tl' | 'tr', `size` px across), a
    full-screen `behind` layer (host html, an image or a video) plays under it on the brand ground, and on `back` the
    circle grows back into the plate. face: (x, y, h) or [(t, x, y, h), ...] in screen px (the face box height); fit:
    circle radius in face heights. plate: the host plate's css transform {x, y, scale, ox, oy} (identity = a full
    frame plate); clip: the plate's visible screen region (x0, y0, x1, y1), e.g. (0, 960, 1080, 1920) under a split
    seam. Inside one shot only (module doc)."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "push")
    t_end0 = self.until(until, t_in, 4.0, cur)
    t_back = cur(back, 0.0, "push", rel=t_end0 - OUT_DUR) if back is not None else t_end0 - OUT_DUR
    t_back = max(t_back, t_in + IN_DUR + 0.3)
    t_end = t_back + OUT_DUR
    size = float(size)
    pid = self.uid("hb")
    trk = track if track is not None else self.track(30)
    region, clip_css = _region(clip)
    btrk = self.track(31) if str(behind or "").endswith((".mp4", ".mov", ".webm")) else None
    cxy = _corner(corner, size, x, y)
    face_fr = _smooth(face, t_in, t_end)
    rows = _rows(t_in, t_back, t_end, face_fr, cxy, size, fit, region)
    pl = plate or {}
    place = (f"transform:translate({pl.get('x', 0)}px,{pl.get('y', 0)}px) scale({pl.get('scale', 1)});"
             f"transform-origin:{pl.get('ox', 540)}px {pl.get('oy', 0)}px")
    vig = (f'<div class="hb-vig" style="background:radial-gradient(125% 88% at 50% 44%,rgba(0,0,0,0) 56%,'
           f'rgba(12,8,6,{float(vignette):.3f}) 100%)"></div>' if vignette else "")
    lab_top = cxy[1] + size / 2 + 22
    lab = (f'<div class="hb-label" style="left:{cxy[0]:.0f}px;top:{lab_top:.0f}px" {box("text", t_in + IN_DUR, t_back)}>'
           f'{esc(label)}</div>' if label else "")
    inner = ((f'<div class="hb-ground"></div>' if ground else "") + f'<div class="hb-behind">{_behind(behind, t_in, t_end, btrk)}</div>'
             f'<div class="hb-move"><div class="hb-shadow"></div><div class="hb-clip" style="clip-path:{clip_css}">'
             f'<div class="hb-mask"><div class="hb-place" style="{place}"><div class="hb-cam">'
             + _video(src, t_in, t_end, trk, media_offset, cls="hb-vid")
             + f'</div></div>{vig}</div></div>' + ('<div class="hb-ring"></div>' if ring else "") + f'</div>{lab}')
    zs = f"z-index:{z};" if z is not None else ""
    html = (f'<div class="rrk rrk-bubble" id="{pid}" data-layout-allow-overflow style="left:0;top:0;width:{W}px;'
            f'height:{H}px;{zs}{self.vars("light")}">{inner}</div>')
    cfg = {"t_in": t_in, "back": t_back, "end": t_end, "rows": rows, "ring": 7.0 if ring else 0.0, "gap": 0.0,
           "lab_in": t_in + IN_DUR - 0.08, "lab_out": t_back}
    ev = [sfx(t_in + 0.05, "whoosh", "head into bubble"), sfx(t_back, "whoosh", "bubble back to the plate")]
    bub = [cxy[0] - size / 2, cxy[1] - size / 2, size, size]
    return self._piece("head-bubble", pid, html, "bubble", cfg, ev, t_in, t_end,
                       {"times": {k: cfg[k] for k in ("t_in", "back", "end")}, "bubble": bub, "corner": corner,
                        "cam_sel": f"#{pid} .hb-cam", "track": trk, "keys": len(rows)})


PIP = {"head_bubble": head_bubble}
