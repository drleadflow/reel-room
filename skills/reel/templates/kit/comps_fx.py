"""Kit components, FX family: comment_dm, stepper, annotate, phone, before_after, spotlight.
Each is a Kit method returning a Piece. See references/kit.md for the args.
The comment-cta flow (field types the keyword on the word, posts, reply lands) is adapted from reel-kit fx/comment-cta
(Copyright (c) 2026 Justyn Berkovits, MIT License, see THIRD_PARTY_NOTICES.md); the DM hand-off is Reel Room's."""
import math
import random

from rrkit_base import W, H, FPS, box, esc, place, sfx

PERSON = ('<svg viewBox="0 0 48 48"><circle cx="24" cy="19" r="8"/><path d="M8 46 C9.5 34 16 29.5 24 29.5 '
          'C32 29.5 38.5 34 40 46 Z"/></svg>')
HEART = ('<svg viewBox="0 0 48 48"><path class="cm-hl" d="M24 40 C10 31 6 24 6 17.5 C6 12 10 8 15 8 C19 8 22 10.5 24 14 '
         'C26 10.5 29 8 33 8 C38 8 42 12 42 17.5 C42 24 38 31 24 40 Z"/></svg>')
LINK = ('<svg viewBox="0 0 48 48"><path d="M20 28 L28 20 M17 23 L12 28 a7 7 0 0 0 10 10 L27 33 M31 25 L36 20 '
        'a7 7 0 0 0 -10 -10 L21 15"/></svg>')
SEND = '<svg viewBox="0 0 48 48"><path d="M8 24 L40 9 L31 40 L23 27 Z M23 27 L40 9"/></svg>'
RAIL = {"heart": HEART.replace(' class="cm-hl"', ''),
        "comment": '<svg viewBox="0 0 48 48"><path d="M24 8 C34 8 41 14.5 41 23 C41 31.5 34 38 24 38 C21 38 18.5 37.5 '
                   '16 36.5 L8 40 L10.5 32.5 C8.3 30 7 26.8 7 23 C7 14.5 14 8 24 8 Z"/></svg>',
        "send": SEND}


def _wrap(pid, comp, x, y, w, h, kit, theme, inner, z=None):
    zs = f"z-index:{z};" if z is not None else ""
    return (f'<div class="rrk rrk-{comp}" id="{pid}" data-layout-allow-overflow style="left:{x}px;top:{y}px;width:{w}px;'
            f'height:{h}px;{zs}{kit.vars(theme)}">{inner}</div>')


def _video(src, t0, t1, track, offset=0.0, filt=None, cls="k-vid"):
    """A frame-synced copy of a video (same frame as the plate under it): own wrapper, exact media start, the
    renderer's coverage gate satisfied (data-duration = window + 3 frames)."""
    f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
    start = max(0.0, math.floor((f0 / FPS - 0.002) * 1e5) / 1e5)
    dur = (f1 - f0 + 3) / FPS
    st = f' style="filter:{filt}"' if filt else ""
    return (f'<div class="{cls}"><video id="kv{track}" src="{esc(src)}" muted playsinline data-start="{start:.5f}" '
            f'data-media-start="{f0 / FPS + offset:.5f}" data-duration="{dur:.5f}" data-track-index="{track}"{st}></video></div>')


def _initials(kit):
    name = kit.brand.get("name") or kit.brand.get("handle") or "RR"
    parts = [p for p in str(name).replace("Dr.", "").replace("@", "").split() if p[:1].isalpha()]
    return ("".join(p[0] for p in parts[-2:]) or "RR").upper()


# ---------------------------------------------------------------------------------------------- 7. comment -> DM
def comment_dm(self, keyword, at=0.0, type_at=None, post=None, dm_at=None, until=None, handle=None, viewer="you",
               comment=None, dm_text=None, link_text=None, link_sub=None, avatar=None, pos="top", x=None, y=None,
               w=900, theme="light", exit="lift", z=None):
    """An Instagram comment field types `keyword` on its word and posts (heart), then the DM lands: typing dots,
    the creator's message, a link card with the keyword. Generic UI in brand colours, no platform logos."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    ty0 = max(cur(type_at, 0.4, "type", rel=t_in), t_in + 0.3)
    ty1 = ty0 + max(0.3, 0.07 * len(keyword))
    t_post = max(cur(post, 0.3, "visual", rel=ty1), ty1 + 0.12)
    t_dm = max(cur(dm_at, 0.5, "visual", rel=t_post), t_post + 0.35)
    t_msg = t_dm + 0.62
    t_link = t_msg + 0.32
    t_out = self.until(until, t_in, t_link + 1.3 - t_in, cur)
    handle = handle or ("@" + self.brand["handle"] if self.brand.get("handle") else "@you")
    dm_text = dm_text or f"Here's your {keyword} link"
    link_text = link_text or f"{keyword.title()} guide"
    link_sub = link_sub or "Tap to open"
    h = 560
    px, py = place(pos, w, h, x, y)
    pid = self.uid("cm")
    av = (f'<img src="{esc(avatar)}" alt="">' if avatar else f'<b>{esc(_initials(self))}</b>')
    typed = "".join(f'<span class="c">{esc(c)}</span>' for c in keyword)
    pre = f'<span class="cm-pre">{esc(comment)} </span>' if comment else ""
    inner = (f'<div class="cm-field" {box("card", t_in, t_out, False)}><div class="cm-av cm-anon">{PERSON}</div>'
             f'<div class="cm-meta"><b>{esc(viewer)}</b> <i>now</i></div><div class="cm-ph">Add a comment...</div>'
             f'<div class="cm-txt" {box("text", ty0, t_out)}>{pre}<span class="cm-typed">{typed}</span><span class="cm-caret"></span></div>'
             f'<div class="cm-post">Post</div><div class="cm-heart">{HEART}</div></div>'
             f'<div class="cm-dm" {box("card", t_dm, t_out, False)}><div class="cm-head"><div class="cm-av cm-me">{av}</div>'
             f'<div class="cm-who"><b>{esc(handle)}</b><span>Active now</span></div><div class="cm-sendic">{SEND}</div></div>'
             f'<div class="cm-dots"><i></i><i></i><i></i></div>'
             f'<div class="cm-bub" {box("text", t_msg, t_out)}>{esc(dm_text)}</div>'
             f'<div class="cm-link" {box("text", t_link, t_out)}><div class="cm-lic">{LINK}</div><div class="cm-lt">'
             f'<b>{esc(link_text)}</b><span>{esc(link_sub)}</span></div><div class="cm-kw">{esc(keyword)}</div></div>'
             f'<div class="cm-seen">Seen</div></div>')
    html = _wrap(pid, "comment", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "ty0": ty0, "ty1": ty1, "post": t_post, "dm": t_dm, "msg": t_msg, "link": t_link, "out": t_out,
           "exit": exit}
    ev = [sfx(t_in, "pop", "comment field"), sfx(t_post, "click", "post"), sfx(t_dm, "whoosh", "dm arrives"),
          sfx(t_link, "pop", "link card", "full"), sfx(t_msg, "pop", "message", "full")]
    ev += [sfx(ty0 + (ty1 - ty0) * i / max(1, len(keyword)), "type", "typing", "full") for i in range(0, len(keyword), 2)]
    return self._piece("comment-cta", pid, html, "comment", cfg, ev, t_in, t_out + 0.2,
                       {"keyword": keyword, "times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 8. stepper
def stepper(self, steps, at=0.0, active=None, until=None, layout="list", kicker="PART", pos=None, x=None, y=None,
            w=None, theme="light", card=True, title=None, exit="blur", z=None):
    """A step tracker. active: one anchor per step (None = no activation); each lights its row (pill fills, number
    and label flip to light, a small punch) and the previous one turns done (check). layout 'list' (side column)
    or 'bar' (segmented HUD with PART 01 / 05 and the current label)."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    acts = []
    for i, _ in enumerate(steps):
        spec = (active or [None] * len(steps))[i] if i < len(active or []) else None
        if spec is None:
            acts.append(None)
            continue
        acts.append(max(cur(spec, 0.6, "visual", rel=max([a for a in acts if a] or [t_in])), t_in + 0.35))
    last = max([a for a in acts if a] or [t_in])
    t_out = self.until(until, t_in, last + 1.3 - t_in, cur)
    n = len(steps)
    pid = self.uid("sp")
    if layout == "bar":
        w = w or 900
        h = 172
        px, py = place(pos or "top", w, h, x, y)
        segs = "".join(f'<div class="st-seg"><i></i></div>' for _ in steps)
        labs = "".join(f'<div class="st-cur" {box("text", acts[i] or t_in, t_out)}>{esc(s)}</div>' for i, s in enumerate(steps))
        inner = (f'<div class="st-bar" {box("card", t_in, t_out, False)}><div class="st-kick" {box("glyph", t_in, t_out)}>'
                 f'<span>{esc(kicker)}</span> <b class="st-n"><span class="st-roll">'
                 + "".join(f"<em>{i + 1:02d}</em>" for i in range(n))
                 + f'</span></b><span> / {n:02d}</span></div><div class="st-labs">{labs}</div>'
                 f'<div class="st-segs">{segs}</div></div>')
    else:
        w = w or 440
        row, pad = 104, (26 if card else 0)
        top = (86 if title else 0) + pad
        h = n * row + top + pad - 16
        px, py = place(pos or "left", w, h, x, y)
        rows = "".join(
            f'<div class="st-row" style="top:{top + i * row}px;left:{pad}px;width:{w - 2 * pad}px"><div class="st-bg"></div><div class="st-num"><span>{i + 1:02d}</span>'
            f'<svg viewBox="0 0 48 48"><path pathLength="1" d="M14 25 L21 32 L34 17"/></svg></div>'
            f'<div class="st-l" {box("text", t_in, t_out)}>{esc(s)}</div></div>' for i, s in enumerate(steps))
        ttl = f'<div class="st-ttl" {box("text", t_in, t_out)}>{esc(title)}</div>' if title else ""
        inner = f'<div class="st-list{" st-card" if card else ""}">{ttl}{rows}</div>'
    html = _wrap(pid, "stepper", px, py, w, h, self, theme, inner, z)
    cfg = {"t_in": t_in, "acts": acts, "out": t_out, "layout": layout, "exit": exit, "n": n}
    ev = [sfx(t_in, "whoosh", "steps in")] + [sfx(a, "tick", f"step {i + 1}") for i, a in enumerate(acts) if a]
    return self._piece("stepper", pid, html, "stepper", cfg, ev, t_in, t_out + 0.2,
                       {"steps": steps, "times": cfg, "box": [px, py, w, h]})


# ---------------------------------------------------------------------------------------------- 9. annotation
def _wobble(pts, amp, seed):
    rnd = random.Random(seed)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i - 1], pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        k = (rnd.random() - 0.5) * 2 * amp
        out.append((pts[i][0] - dy / L * k, pts[i][1] + dx / L * k))
    out.append(pts[-1])
    return out


def _smooth(pts):
    """Catmull-Rom through the points -> cubic Bezier path."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def _arrow(a, b, bend, seed, head=50):
    (x0, y0), (x1, y1) = a, b
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    cx, cy = (x0 + x1) / 2 - dy / L * bend * L, (y0 + y1) / 2 + dx / L * bend * L
    pts = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1)
           for t in [i / 14 for i in range(15)]]
    shaft = _smooth(_wobble(pts, 2.6, seed))
    tx, ty = x1 - pts[-2][0], y1 - pts[-2][1]
    ang = math.atan2(ty, tx)
    heads = []
    for s in (-1, 1):
        a2 = ang + math.pi - s * math.radians(28)
        hx, hy = x1 + math.cos(a2) * head, y1 + math.sin(a2) * head
        mx, my = (x1 + hx) / 2 + s * 3, (y1 + hy) / 2 - 2
        heads.append(f"M{x1:.1f} {y1:.1f} Q{mx:.1f} {my:.1f} {hx:.1f} {hy:.1f}")
    return [shaft] + heads


def _loop(bx, by, bw, bh, pad, seed):
    rnd = random.Random(seed)
    cx, cy, rx, ry = bx + bw / 2, by + bh / 2, bw / 2 + pad, bh / 2 + pad
    a0, turns, n = math.radians(-118), 1.13, 40
    pts = []
    for i in range(n + 1):
        t = i / n
        a = a0 + t * turns * 2 * math.pi
        k = 1 + 0.07 * t + (rnd.random() - 0.5) * 0.025
        pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    return [_smooth(pts)]


def _under(bx, by, bw, bh, seed, double=False):
    out = []
    for j in range(2 if double else 1):
        y0 = by + bh + 14 + j * 22
        pts = [(bx - 10 + bw * t * 1.04, y0 + math.sin(t * 3.1 + j) * 5 - t * 6 * (1 - j)) for t in [i / 8 for i in range(9)]]
        out.append(_smooth(_wobble(pts, 2.0, seed + j)))
    return out


def annotate(self, target, kind="arrow", at=0.0, label=None, frm=None, label_at=None, until=None, color="accent",
             width=9, bend=0.22, size=84, seed=7, pad=26, double=False, exit="erase", z=None):
    """A hand-drawn mark that draws on: kind 'arrow' (from `frm` to the point `target`), 'circle' (a loop around
    the box `target` = (x, y, w, h)) or 'underline' (under the box). `label` is written by hand next to the start."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    t_lab = cur(label_at, 0.0, "visual", rel=t_in) if label else None
    t_out = self.until(until, t_in, 1.8, cur)
    col = self.color(color)
    pid = self.uid("an")
    lab_html, lx, ly = "", None, None
    if kind == "arrow":
        tx, ty = target[:2]
        fx, fy = frm or (tx - 300, ty - 260)
        paths = _arrow((fx, fy), (tx, ty), bend, seed)
        lx, ly = fx, fy
    elif kind == "circle":
        paths = _loop(*target, pad, seed)
        lx, ly = target[0] + target[2] + pad + 10, target[1] - pad
    else:
        paths = _under(*target, seed, double)
        lx, ly = target[0], target[1] + target[3] + 40
    if label:
        est = len(label) * size * 0.42
        side = "right" if lx > W / 2 else "left"
        left = max(40, min(W - 40 - est, lx - est - 16 if side == "right" else lx - est / 2))
        top = ly - size * 1.05 if kind == "arrow" else ly
        lab_html = (f'<div class="an-lab" style="left:{left:.0f}px;top:{top:.0f}px;font-size:{size}px;color:{col}" '
                    f'{box("text", t_lab or t_in, t_out)}>' + "".join(f'<span class="c">{esc(c)}</span>' for c in label) + "</div>")
    svg = (f'<svg class="an-svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
           + "".join(f'<path pathLength="1" d="{d}" stroke="{col}" stroke-width="{width if i == 0 else width - 1}"/>'
                     for i, d in enumerate(paths)) + "</svg>")
    html = _wrap(pid, "annotate", 0, 0, W, H, self, "light", svg + lab_html, z)
    cfg = {"t_in": t_in, "lab": t_lab, "out": t_out, "kind": kind, "exit": exit}
    ev = [sfx(t_in, "flip", f"{kind} draws")]
    if t_lab is not None and abs(t_lab - t_in) > 0.3:
        ev.append(sfx(t_lab, "flip", "label", "full"))
    return self._piece("annotation-arrow", pid, html, "annotate", cfg, ev, t_in, t_out + 0.25,
                       {"kind": kind, "times": cfg, "label_xy": [lx, ly]})


# ---------------------------------------------------------------------------------------------- 10. phone frame
def phone(self, at=0.0, back=None, until=None, src="assets/aroll.mp4", media_offset=0.0, cx=540, cy=900, scale=0.5,
          radius=70, ring=18, tilt=5, chrome="reel", handle=None, caption=None, title=None, track=None, z=None):
    """The speaker shrinks into a phone frame (a frame-synced copy of `src` inside a bezel over the brand ground)
    and grows back out on `back` (default 0.65 s before `until`). chrome 'reel' (side rail + handle + caption),
    'app' (status bar only) or None."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "push")
    t_end = self.until(until, t_in, 3.0, cur)
    t_back = cur(back, 0.0, "push", rel=t_end - 0.65) if back is not None else t_end - 0.65
    t_back = max(t_back, t_in + 0.9)
    t_end = max(t_end, t_back + 0.62)
    pid = self.uid("ph")
    trk = track if track is not None else self.track(30)
    k = float(scale)
    handle = handle or ("@" + self.brand["handle"] if self.brand.get("handle") else "")
    inv = 1 / k
    chrome_html = ""
    if chrome:
        rail = "".join(f'<div class="ph-ri">{RAIL[n]}<span>{c}</span></div>'
                       for n, c in (("heart", "12.4K"), ("comment", "318"), ("send", "Share")))
        rail_html = f'<div class="ph-rail">{rail}</div>' if chrome == "reel" else ""
        foot = (f'<div class="ph-foot"><div class="ph-hd"><i></i><b>{esc(handle)}</b><em>Follow</em></div>'
                f'<div class="ph-cap">{esc(caption or "")}</div></div>' if chrome == "reel" else "")
        chrome_html = (f'<div class="ph-chrome" style="transform:scale({inv:.4f});width:{W * k:.0f}px;height:{H * k:.0f}px">'
                       f'<div class="ph-status"><b>9:41</b><span class="ph-isl"></span><i></i></div>{rail_html}{foot}</div>')
    ttl = (f'<div class="ph-title" {box("text", t_in + 0.4, t_back)}>{esc(title)}</div>' if title else "")
    inner = (f'<div class="ph-back"></div>{ttl}<div class="ph-persp"><div class="ph-stage">'
             + _video(src, t_in, t_end, trk, media_offset, cls="ph-vid")
             + f'{chrome_html}<div class="ph-bezel"></div></div></div>')
    html = _wrap(pid, "phone", 0, 0, W, H, self, "light", inner, z)
    cfg = {"t_in": t_in, "back": t_back, "end": t_end, "k": k, "cx": cx, "cy": cy, "R": radius / k, "ring": ring / k,
           "tilt": tilt}
    ev = [sfx(t_in + 0.05, "whoosh", "shrink into phone"), sfx(t_back, "whoosh", "back to full frame")]
    return self._piece("phone-frame", pid, html, "phone", cfg, ev, t_in, t_end,
                       {"times": cfg, "screen": [cx - W * k / 2, cy - H * k / 2, W * k, H * k], "track": trk})


# ---------------------------------------------------------------------------------------------- 11. before / after
def before_after(self, at=0.0, sweep=None, until=None, before=None, after=None, mode="full", rest=0.6, end=0.0,
                 labels=("BEFORE", "AFTER"), angle=7, src="assets/aroll.mp4", media_offset=0.0,
                 before_filter="saturate(0.12) contrast(0.84) brightness(1.07)", card=None, track=None, z=None):
    """A tilted divider wipes BEFORE into AFTER. mode 'full': over the whole frame; before = None uses a live
    frame-synced copy of the plate with `before_filter` (a look wipe), after = None lets the plate show through.
    mode 'card': a rounded card at `card` = (x, y, w, h) with before/after images. The divider lands at `rest`
    (share of BEFORE still showing) on `at`, then sweeps to `end` on `sweep`."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "visual")
    t_sw = max(cur(sweep, 1.2, "visual", rel=t_in), t_in + 0.7) if sweep is not False else None
    t_out = self.until(until, t_in, ((t_sw or t_in) + 1.4) - t_in, cur)
    pid = self.uid("ba")
    trk = track if track is not None else self.track(30)
    if mode == "card":
        bx, by, bw, bh = card or (90, 250, 900, 620)
    else:
        bx, by, bw, bh = 0, 0, W, H

    def layer(spec, is_before):
        if spec is None and is_before:
            return _video(src, t_in, t_out, trk, media_offset, before_filter, cls="ba-media")
        if spec is None:
            return ""
        s = str(spec)
        if s.endswith((".mp4", ".mov", ".webm")):
            return _video(s, t_in, t_out, trk + (0 if is_before else 1), 0.0, cls="ba-media")
        return f'<div class="ba-media" style="background-image:url(\'{esc(s)}\')"></div>'
    ly = 260 if mode == "full" else 34
    lab_b = f'<div class="ba-tag ba-tb" style="top:{ly}px" {box("text", t_in, t_out)}>{esc(labels[0])}</div>'
    lab_a = f'<div class="ba-tag ba-ta" style="top:{ly}px" {box("text", t_in, t_out)}>{esc(labels[1])}</div>'
    inner = (f'<div class="ba-box{" ba-card" if mode == "card" else ""}" {box("card", t_in, t_out, False)}>'
             f'<div class="ba-after">{layer(after, False)}{lab_a}</div>'
             f'<div class="ba-before">{layer(before, True)}{lab_b}</div>'
             f'<div class="ba-div"><i class="ba-line"></i><div class="ba-knob"><svg viewBox="0 0 48 48">'
             f'<path d="M19 15 L10 24 L19 33 M29 15 L38 24 L29 33"/></svg></div></div></div>')
    html = _wrap(pid, "before-after", bx, by, bw, bh, self, "light", inner, z)
    cfg = {"t_in": t_in, "sweep": t_sw, "out": t_out, "rest": rest, "end": end, "angle": angle, "w": bw, "h": bh,
           "mode": mode}
    ev = [sfx(t_in, "flip", "divider lands")] + ([sfx(t_sw, "flip", "sweep")] if t_sw else [])
    return self._piece("before-after", pid, html, "beforeAfter", cfg, ev, t_in, t_out + 0.2,
                       {"times": cfg, "box": [bx, by, bw, bh], "track": trk})


# ---------------------------------------------------------------------------------------------- 12. spotlight
def _geom(t, pad):
    if len(t) == 3:
        cx, cy, r = t
        return [cx - r - pad, cy - r - pad, 2 * (r + pad), 2 * (r + pad)]
    x, y, w, h = t
    return [x - pad, y - pad, w + 2 * pad, h + 2 * pad]


def spotlight(self, target, at=0.0, moves=None, until=None, shape="round", dim=0.62, feather=18, ring=True,
              label=None, pad=20, color="accent", z=None):
    """Dims the frame except one region (target = (x, y, w, h) box or (cx, cy, r) circle). moves = [(anchor,
    target), ...] glide the light to the next thing. A thin brand ring marks the region; label = one text or a list
    (one per stop, None = no label at that stop)."""
    cur = self.cursor()
    t_in = cur(at, 0.0, "push")
    ks = [[t_in] + _geom(target, pad)]
    for spec, tg in (moves or []):
        t = max(cur(spec, 1.0, "push", rel=ks[-1][0]), ks[-1][0] + 0.45)
        ks.append([t] + _geom(tg, pad))
    t_out = self.until(until, t_in, ks[-1][0] + 1.2 - t_in, cur)
    pid = self.uid("sl")
    col = self.color(color)
    ink = self.brand["colors"]["ink"]
    r, g, b = (int(ink[i:i + 2], 16) for i in (1, 3, 5))
    rad = "50%" if shape == "round" else "36px"
    labs = label if isinstance(label, (list, tuple)) else [label] + [None] * len(moves or [])
    lab = "".join(f'<div class="sl-lab" data-k="{i}" style="background:{col}" {box("text", ks[min(i, len(ks) - 1)][0] + 0.4, t_out)}>'
                  f'{esc(t)}</div>' for i, t in enumerate(labs) if t)
    inner = (f'<div class="sl-hole" style="border-radius:{rad};box-shadow:0 0 0 3000px rgba({r},{g},{b},{dim});'
             f'filter:blur({feather}px)"></div>'
             + (f'<div class="sl-ring" style="border-radius:{rad};border-color:{col}"></div>' if ring else "") + lab)
    html = _wrap(pid, "spotlight", 0, 0, W, H, self, "light", inner, z)
    cfg = {"t_in": t_in, "keys": ks, "out": t_out}
    ev = [sfx(t_in, "whoosh", "spotlight")] + [sfx(k[0], "flip", "light moves", "full") for k in ks[1:]]
    return self._piece("spotlight", pid, html, "spotlight", cfg, ev, t_in, t_out + 0.3, {"times": cfg})


FX = {"comment_dm": comment_dm, "stepper": stepper, "annotate": annotate, "phone": phone, "before_after": before_after,
      "spotlight": spotlight}
