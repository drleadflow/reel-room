"""beats_editorial: showcase everyday beats (the non-hero lines). Each is a calm, editorial treatment on the
section's colour set, built to replace the plain white pill card:

  ed-headline   a serif headline on a colour ground, an italic sub-line under it
  ed-number     a number slams in serif, a small mono context line sits above it
  ed-checklist  a small editorial checklist card: header rule, rows that tick on their words
  ed-contrast   'A -> B': A is struck through on its word, B lands in italic accent
  ed-kicker     a mono kicker line over a serif headline (lockup)

Layouts: "split" (the 1080x960 top slot: colour-set ground + the editorial meta row are there from the beat's first
frame, the type is readable within 0.15 s, the payoff lands on its word) and "full" / "overlay" (a compact card in the
band above the head over full-frame footage, e.g. editorial-ui room cuts; `area` = [y0, y1] of that band).
Contracts: BEATS (engine/beat_schema.py validates fills: spoken words and numbers only, anchors in the line).
Registered additively into rrkit (register(Kit, COMPONENTS)); never in the hero catalogue. Reel Room's own code.
"""
from heroes_base import JS, Clock, Stage, box, esc, make, root, sfx, text_px

BEATS = {}
CARD_W = 900
BAND_K = 0.42          # band cards (full-frame footage) set their type at this share of the split size: small UI cards
SUB_MIN_PX = 30
FLY = {"opacity": 0.5, "y": 110, "rotationX": -62, "scale": 0.9, "filter": "blur(14px)", "transformPerspective": 1100}
EASE_IN = "back.out(1.5)"     # every entrance is an eased slide with a small overshoot (judge: no plain fades)
EASE_OUT = "back.in(1.6)"


def beat(bid, method, fields, what, min_secs=1.0):
    """Declare an everyday beat. fields: {name: (type, opts)} with the hero_schema types (text, texts, anchor,
    anchors, set, bool)."""
    def deco(fn):
        BEATS[bid] = {"id": bid, "method": method, "fields": fields, "what": what, "min_secs": float(min_secs),
                      "layouts": ["split", "full", "overlay"], "fn": fn}
        return fn
    return deco


SAY = {"ed-headline": ["editorial headline card", "serif headline with an italic line", "headline card"],
       "ed-number": ["slam the number", "big number card", "the stat lands"],
       "ed-checklist": ["editorial checklist", "tick the list", "checklist card"],
       "ed-contrast": ["strike A, land B", "this, not that", "contrast card"],
       "ed-kicker": ["kicker over the headline", "small caps lead-in, big headline", "kicker card"]}


def register(Kit, COMPONENTS):
    for bid, c in BEATS.items():
        setattr(Kit, c["method"], c["fn"])
        COMPONENTS[bid] = {"method": c["method"], "say": SAY.get(bid) or [c["what"]], "what": c["what"], "beat": True,
                           "layouts": c["layouts"], "min_secs": c["min_secs"]}


# ---------------------------------------------------------------------------------------------- shared frame
CSS = (".rrb{position:absolute;left:0;width:1080px}"
       ".rrb .eb-card{position:absolute;left:0;right:0;margin:0 auto;width:fit-content;min-width:0;max-width:900px;"
       "border-radius:30px;background:var(--h-card);box-shadow:var(--h-shadow);padding:30px 40px 32px;"
       "box-sizing:border-box}.rrh-full .rrb .eb-kick{font-size:20px}.rrh-full .rrb .eb-card{padding:22px 34px 24px}"
       ".rrh-full .rrb .eb-rule{margin-top:10px}"
       ".rrb .eb-kick{font:600 26px/1.2 var(--h-fm);letter-spacing:.16em;text-transform:uppercase;color:var(--h-sub);"
       "white-space:nowrap;display:inline-block}"
       ".rrb .eb-rule{height:2px;background:var(--h-line);margin:16px 0 0;transform-origin:0 50%}"
       ".rrb .eb-h{font-family:var(--k-fs);font-weight:800;line-height:.98;letter-spacing:-.015em;color:var(--h-ink);"
       "text-transform:uppercase;white-space:nowrap}"
       ".rrb .eb-i{font-family:var(--k-fs);font-style:italic;font-weight:600;line-height:1.05;color:var(--h-acc);"
       "white-space:nowrap}"
       ".rrb .eb-m{display:block;padding:.04em 0 .1em}"
       ".rrb .eb-m > span{display:inline-block}.rrb .eb-sub{margin-top:.14em}"
       ".rrb .eb-bar{display:block;height:9px;border-radius:5px;background:var(--h-hl);transform-origin:0 50%;margin-top:18px}")


class Frame:
    """Geometry + entrance helpers for one beat: split slot (left-aligned type on the ground) or a band card."""

    def __init__(self, kit, layout, area, comp, tone):
        self.kit, self.stage, self.comp, self.tone = kit, Stage(layout, area[:2] if area else None), comp, tone
        self.stage_area = list(area) if area else None
        self.split = self.stage.layout == "split"
        self.pid = kit.uid(comp.replace("ed-", "eb"))
        self.js = JS(self.pid)
        self.js.split = self.split

    @property
    def side(self):
        """(x, max width) when the adapter puts a band card beside the head (area = [y0, y1, x, w])."""
        a = self.stage_area
        return (int(a[2]), int(a[3])) if a and len(a) >= 4 else None

    @property
    def width(self):
        if self.split:
            return 930
        return (self.side[1] if self.side else CARD_W) - 76

    def px(self, text, big, k=0.66, lo=60):
        """Font size that fits `text` on one line in the frame (smaller in a band card)."""
        return text_px(str(text).upper(), self.width, big if self.split else int(big * BAND_K), k=k, lo=lo)

    def fit(self, px, per_px, fixed, lo=26):
        """Band cards: shrink the type so the card (fixed px + per_px x font size) fits its band's height."""
        if self.split:
            return px
        room = self.stage.h - 12 - fixed
        return int(max(lo, min(px, room / per_px)))

    def wrap(self, inner, h_est):
        """The beat's block: split -> straight on the ground, centred in the safe band; band -> a card."""
        if self.split:
            top = round(self.stage.y0 + max(0, (self.stage.h - h_est) / 2))
            return f'<div class="rrb eb-blk" style="top:{top}px;padding-left:72px;box-sizing:border-box">{inner}</div>'
        top = self.stage.y0 + 6
        pos = (f' style="left:{self.side[0]}px;right:auto;margin:0;min-width:0;max-width:{self.side[1]}px"'
               if self.side else "")
        return f'<div class="rrb eb-blk" style="top:{top}px"><div class="eb-card"{pos}>{inner}</div></div>'

    def html(self, inner, h_est, css=""):
        return root(self.pid, self.comp, self.kit, self.tone, self.wrap(inner, h_est) + self.js.svg_defs(), self.stage,
                    full=not self.split, extra_css=CSS + css)

    def rise(self, sel, t, stagger=None):
        """Type rises into place with a little blur (the showcase entrance; no clipping mask, so QA never sees the line
        cut off by its panel mid-rise)."""
        self.js.ft(sel, {"opacity": 0, "y": 46, "filter": "blur(8px)"},
                   {"opacity": 1, "y": 0, "filter": "blur(0px)"}, t, 0.46, EASE_IN, stagger=stagger)

    def start(self, t_in, t_out):
        self.js.life(t_in, t_out + 0.24)
        if self.split:
            self.js.ground_in(t_in, 0.42)
        else:
            # the editorial-ui card fly-in (3D tilt, blur, from below; half visible on its own frame)
            self.js.ft(".eb-card", FLY, {"opacity": 1, "y": 0, "rotationX": 0, "scale": 1, "filter": "blur(0px)"},
                       t_in, 0.55, EASE_IN)

    def end(self, t_out):
        self.js.to(".eb-blk", {"opacity": 0, "y": -56, "scale": 0.94, "filter": "blur(6px)"}, t_out, 0.24, EASE_OUT)


def _lines(text, n_max=2, one_line=14):
    words = str(text).split()
    if len(str(text)) <= one_line or len(words) < 2 or n_max < 2:
        return [str(text)]
    i = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
    return [" ".join(words[:i]), " ".join(words[i:])]


def _mask(cls, text, px, t0, t1, fit=None, extra=""):
    fit = f' data-fit="{fit},40"' if fit else ""
    return (f'<span class="eb-m"><span class="{cls}" style="font-size:{px}px"{fit}{extra} {box("text", t0, t1)}>'
            f'{esc(text)}</span></span>')


def clamp(kit, t_in, t_out, min_show=0.9):
    """Never past the beat's end (a card must not linger over the next cut): t_out <= the kit's default_until; a
    card that would then be too short enters earlier instead."""
    cap = getattr(kit, "default_until", None)
    if cap is None or t_out <= cap:
        return t_in, t_out
    return max(kit.base, min(t_in, cap - min_show)), cap


def _times(fr, at, land, until, need):
    ck = Clock(fr.kit, at)
    t_in = ck.t_in
    t_land = ck.at(land, 0.3, "stamp")
    t_in, t_out = clamp(fr.kit, t_in, ck.end(until, max(t_land, t_in + need) + 0.5))
    return ck, t_in, min(t_land, t_out - 0.3), t_out


# ---------------------------------------------------------------------------------------------- ed-headline
@beat("ed-headline", "ed_headline",
      fields={"text": ("text", (28, True)), "sub": ("text", (30, False)), "at": ("anchor", ()), "land": ("anchor", ()),
              "sub_at": ("anchor", ()), "until": ("anchor", ()), "tone": ("set", ())},
      what="a serif headline on the section's colour ground; an italic sub-line follows; the accent rule draws on the "
           "word", min_secs=1.0)
def ed_headline(self, text, sub=None, at=0.0, land=None, sub_at=None, until=None, tone="cream", layout="split",
                area=None, z=None):
    fr = Frame(self, layout, area, "ed-headline", tone)
    ck, t_in, t_land, t_out = _times(fr, at, land, until, 0.9)
    t_text = t_in + 0.06
    t_sub = ck.at(sub_at, 0.42, "visual", floor=t_text + 0.25) if sub else None
    lines = _lines(text)
    px = min(fr.px(ln, 190) for ln in lines)
    px = fr.fit(px, len(lines) * 1.12 + (0.66 if sub else 0), 50)
    sub_px = min(int(px * 0.5), text_px(sub or "x", fr.width, 96, k=0.48, lo=24)) if sub else 0
    if sub and not fr.split and sub_px < SUB_MIN_PX:      # a sub-line too small to read on a phone is dropped
        sub, t_sub, sub_px = None, None, 0
        px = fr.fit(min(fr.px(ln, 190) for ln in lines), len(lines) * 1.12, 50)
    rows = "".join(_mask("eb-h", ln, px, t_text + 0.15, t_out, fr.width) for ln in lines)
    rows += _mask("eb-i eb-sub", sub, sub_px, t_sub + 0.1, t_out, fr.width) if sub else ""
    rows += f'<i class="eb-bar" style="width:{min(fr.width, int(px * 2.4))}px"></i>' if fr.split else ""
    fr.start(t_in, t_out)
    fr.rise(".eb-h", t_text, stagger=0.08)
    if sub:
        fr.rise(".eb-sub", t_sub)
    if fr.split:                      # the highlight rule is a split-panel device; band cards stay clean
        fr.js.hide(".eb-bar", {"scaleX": 0})
        fr.js.ft(".eb-bar", {"scaleX": 0}, {"scaleX": 1}, max(t_land, t_text + 0.3), 0.5, "expo.inOut")
    elif t_land > t_text + 0.3:
        fr.js.ft(".eb-card", {"scale": 1.04}, {"scale": 1}, t_land, 0.45, "elastic.out(1,0.45)")
    fr.end(t_out)
    h = len(lines) * px * 1.1 + sub_px * 1.3 + 40
    ev = [sfx(t_in, "whoosh", "colour set"), sfx(t_text, "pop", f"headline {text[:16]}")]
    ev += [sfx(t_sub, "pop", "sub-line", "full")] if sub else []
    return make("ed-headline", self, fr.pid, fr.html(rows, h), fr.js, ev, t_in, t_out + 0.25,
                {"times": {"in": t_in, "text": t_text, "land": t_land, "sub": t_sub, "out": t_out}, "px": px})


# ---------------------------------------------------------------------------------------------- ed-number
NUM_CSS = ".rrb .eb-num{font-family:var(--k-fs);font-weight:800;line-height:.9;letter-spacing:-.03em;color:var(--h-ink);" \
          "white-space:nowrap;display:inline-block;transform-origin:0 80%}" \
          ".rrb .eb-num i{font-style:italic;color:var(--h-acc)}"


@beat("ed-number", "ed_number",
      fields={"value": ("text", (12, True)), "context": ("text", (30, False)), "at": ("anchor", ()),
              "land": ("anchor", ()), "until": ("anchor", ()), "tone": ("set", ())},
      what="a number slams in huge serif on its word; a small mono context line sits above it", min_secs=1.0)
def ed_number(self, value, context=None, at=0.0, land=None, until=None, tone="cream", layout="split", area=None,
              z=None):
    fr = Frame(self, layout, area, "ed-number", tone)
    _ck, t_in, t_land, t_out = _times(fr, at, land, until, 0.9)
    t_num = min(t_land, t_in + (0.45 if fr.split else 0.06))   # never a bare panel; it stamps again on its word
    px = fr.fit(text_px(value, fr.width, 300 if fr.split else 120, k=0.62, lo=72), 1.0, 70 + (50 if context else 0), 48)
    kick = (f'<div class="eb-kick" data-fit="{fr.width},14" {box("text", t_in + 0.2, t_out)}>{esc(context)}</div><i class="eb-rule"></i>'
            if context else "")
    num = (f'<div class="eb-m" style="margin-top:14px"><span class="eb-num" style="font-size:{px}px" '
           f'data-fit="{fr.width},60" {box("glyph", t_num + 0.2, t_out)}>{esc(value)}</span></div>')
    fr.start(t_in, t_out)
    if context:
        fr.rise(".eb-kick", t_in + 0.04)
        fr.js.hide(".eb-rule", {"scaleX": 0})
        fr.js.ft(".eb-rule", {"scaleX": 0}, {"scaleX": 1}, t_in + 0.1, 0.6, "expo.inOut")
    fr.js.ft(".eb-num", {"opacity": 0, "scale": 1.45, "filter": "blur(10px)"},
             {"opacity": 1, "scale": 1, "filter": "blur(0px)"}, t_num, 0.34, "back.out(1.6)")
    if t_land > t_num + 0.25:
        fr.js.ft(".eb-num", {"scale": 1.08}, {"scale": 1}, t_land, 0.42, "elastic.out(1,0.45)")
    fr.end(t_out)
    ev = [sfx(t_in, "whoosh", "colour set"), sfx(t_num, "stamp", f"number {value}")]
    return make("ed-number", self, fr.pid, fr.html(kick + num, px + 90, NUM_CSS), fr.js, ev, t_in, t_out + 0.25,
                {"times": {"in": t_in, "num": t_num, "land": t_land, "out": t_out}, "px": px})


# ---------------------------------------------------------------------------------------------- ed-checklist
CL_CSS = ".rrb .eb-row{display:flex;align-items:center;gap:22px;padding:16px 0;border-bottom:2px solid var(--h-line)}" \
         ".rrb .eb-row:last-child{border-bottom:0}" \
         ".rrb .eb-dot{flex:none;width:44px;height:44px;border-radius:50%;border:3px solid var(--h-line);position:relative}" \
         ".rrb .eb-dot b{position:absolute;inset:-3px;border-radius:50%;background:var(--h-acc)}" \
         ".rrb .eb-dot svg{position:absolute;left:9px;top:10px;width:26px;height:22px}" \
         ".rrb .eb-dot path{fill:none;stroke:var(--h-card);stroke-width:4;stroke-linecap:round;stroke-linejoin:round}" \
         ".rrb .eb-t{font-family:var(--k-fs);font-weight:700;color:var(--h-ink);white-space:nowrap;line-height:1.1}" \
         ".rrb .eb-list{margin-top:10px}"
TICK = '<svg viewBox="0 0 26 22"><path d="M3 11.5l7 7L23 4" pathLength="1" stroke-dasharray="1"/></svg>'


@beat("ed-checklist", "ed_checklist",
      fields={"items": ("texts", (2, 5, 28)), "title": ("text", (28, False)), "ticks": ("anchors", (5,)),
              "at": ("anchor", ()), "until": ("anchor", ()), "tone": ("set", ())},
      what="a small editorial checklist card with a header rule; each row ticks on its word", min_secs=1.4)
def ed_checklist(self, items, title=None, ticks=None, at=0.0, until=None, tone="cream", layout="split", area=None,
                 z=None):
    fr = Frame(self, layout, area, "ed-checklist", tone)
    ck = Clock(self, at)
    t_in = ck.t_in
    tk, cur = list(ticks or []), self.cursor(start=t_in)          # ticks search in spoken order
    times = []
    for i in range(len(items)):
        t = cur(tk[i], 0.45, "visual", rel=times[-1] if times else t_in + 0.05) if i < len(tk) else None
        times.append(round(max(t if t is not None else (times[-1] if times else t_in) + 0.45,
                               t_in + 0.3 + 0.2 * i, (times[-1] + 0.15) if times else 0), 4))
    t_in, t_out = clamp(self, t_in, ck.end(until, max(times) + 0.5), 1.2)
    times = [min(t, t_out - 0.25) for t in times]
    t_px = min(text_px(it, fr.width - 70, 76 if fr.split else 40, k=0.52, lo=30) for it in items)
    t_px = fr.fit(t_px, len(items) * 1.1, 70 + 34 * len(items) + (40 if title else 0), 24)
    head = (f'<div class="eb-kick" data-fit="{fr.width},14" {box("text", t_in + 0.2, t_out)}>{esc(title)}</div>' if title else "")
    rows = "".join(f'<div class="eb-row r{i}"><span class="eb-dot"><b></b>{TICK}</span><span class="eb-m">'
                   f'<span class="eb-t" style="font-size:{t_px}px" data-fit="{fr.width - 70},30" '
                   f'{box("text", t_in + 0.25, t_out)}>{esc(it)}</span></span></div>' for i, it in enumerate(items))
    inner = head + '<i class="eb-rule"></i>' + f'<div class="eb-list">{rows}</div>'
    fr.start(t_in, t_out)
    _cl_js(fr, t_in, times, bool(title))
    fr.end(t_out)
    ev = [sfx(t_in, "whoosh", "checklist card")] + [sfx(t, "tick", f"row {i + 1}") for i, t in enumerate(times)]
    h = len(items) * (t_px * 1.1 + 34) + 60
    return make("ed-checklist", self, fr.pid, fr.html(inner, h, CL_CSS), fr.js, ev, t_in, t_out + 0.25,
                {"times": {"in": t_in, "ticks": times, "out": t_out}, "px": t_px})


def _cl_js(fr, t_in, times, has_title):
    js = fr.js
    if has_title:
        fr.rise(".eb-kick", t_in + 0.04)
    js.hide(".eb-rule", {"scaleX": 0})
    js.ft(".eb-rule", {"scaleX": 0}, {"scaleX": 1}, t_in + 0.08, 0.6, "expo.inOut")
    fr.rise(".eb-t", t_in + 0.1, stagger=0.07)
    for i, t in enumerate(times):
        js.hide(f".r{i} .eb-dot b", {"scale": 0})
        js.ft(f".r{i} .eb-dot b", {"scale": 0}, {"scale": 1}, t, 0.3, "back.out(2)")
        js.hide(f".r{i} .eb-dot path", {"strokeDashoffset": 1})
        js.ft(f".r{i} .eb-dot path", {"strokeDashoffset": 1}, {"strokeDashoffset": 0}, t + 0.08, 0.24, "power2.out")


# ---------------------------------------------------------------------------------------------- ed-contrast
CT_CSS = ".rrb .eb-a{position:relative;display:inline-block;font-family:var(--k-fs);font-weight:700;color:var(--h-sub);" \
         "white-space:nowrap;line-height:1.05}" \
         ".rrb .eb-x{position:absolute;left:-8px;right:-8px;top:54%;height:8px;border-radius:4px;background:var(--h-alert);" \
         "transform-origin:0 50%}" \
         ".rrb .eb-arrow{font:500 54px/1 var(--h-fm);color:var(--h-acc);margin:10px 0 4px;display:block}"


@beat("ed-contrast", "ed_contrast",
      fields={"left": ("text", (28, True)), "right": ("text", (28, True)), "arrow": ("text", (3, False)),
              "at": ("anchor", ()), "a_at": ("anchor", ()), "strike_at": ("anchor", ()), "land": ("anchor", ()),
              "until": ("anchor", ()), "tone": ("set", ())},
      what="'A -> B': A sets in serif on its word and is struck through, B lands in italic accent", min_secs=1.4)
def ed_contrast(self, left, right, arrow="→", at=0.0, a_at=None, strike_at=None, land=None, until=None,
                tone="cream", layout="split", area=None, z=None):
    fr = Frame(self, layout, area, "ed-contrast", tone)
    ck = Clock(self, at)
    t_in = ck.t_in
    t_a = ck.at(a_at, 0.06, "visual", floor=t_in + 0.06)       # the ground is there from the cut, A on its word
    t_strike = min(ck.at(strike_at, 0.55, "visual", floor=t_a + 0.35), t_a + 0.85)   # never a half-empty panel
    t_b = min(ck.at(land, t_strike - t_in + 0.25, "stamp", floor=t_strike + 0.15), t_strike + 0.3)
    t_in, t_out = clamp(self, t_in, ck.end(until, t_b + 0.8), 1.2)
    t_a, t_strike, t_b = (min(x, t_out - d) for x, d in ((t_a, 0.9), (t_strike, 0.6), (t_b, 0.35)))
    t_a = max(t_a, t_in + 0.06)
    a_px = text_px(left, fr.width, 120 if fr.split else 52, k=0.5, lo=36)
    b_px = text_px(right, fr.width, 150 if fr.split else 64, k=0.5, lo=40)
    k = fr.fit(100, 1.0, 140) / 100 if not fr.split else 1.0      # both rows shrink together to fit the band
    a_px, b_px = int(a_px * k), int(b_px * k)
    inner = (f'<span class="eb-m"><span class="eb-a" style="font-size:{a_px}px" data-fit="{fr.width},36" '
             f'{box("text", t_a + 0.15, t_out)}>{esc(left)}<i class="eb-x"></i></span></span>'
             f'<span class="eb-arrow">{esc(arrow if arrow != "->" else "→")}</span>'
             + _mask("eb-i eb-b", right, b_px, t_b + 0.15, t_out, fr.width))
    fr.start(t_in, t_out)
    fr.rise(".eb-a", t_a)
    fr.js.hide(".eb-x", {"scaleX": 0})
    fr.js.ft(".eb-x", {"scaleX": 0}, {"scaleX": 1}, t_strike, 0.28, "power3.inOut")
    fr.js.hide(".eb-arrow", {"opacity": 0})
    fr.js.ft(".eb-arrow", {"opacity": 0, "x": -30}, {"opacity": 1, "x": 0}, t_strike + 0.1, 0.3, EASE_IN)
    fr.rise(".eb-b", t_b)
    fr.end(t_out)
    ev = [sfx(t_in, "whoosh", "contrast card"), sfx(t_strike, "click", "strike"), sfx(t_b, "pop", f"after {right[:12]}")]
    h = a_px * 1.1 + 70 + b_px * 1.1
    return make("ed-contrast", self, fr.pid, fr.html(inner, h, CT_CSS), fr.js, ev, t_in, t_out + 0.25,
                {"times": {"in": t_in, "a": t_a, "strike": t_strike, "b": t_b, "out": t_out}})


# ---------------------------------------------------------------------------------------------- ed-kicker
@beat("ed-kicker", "ed_kicker",
      fields={"kicker": ("text", (30, True)), "text": ("text", (28, True)), "at": ("anchor", ()), "land": ("anchor", ()),
              "until": ("anchor", ()), "tone": ("set", ())},
      what="a mono kicker line types in over a serif headline that lands on its word (lockup)", min_secs=1.0)
def ed_kicker(self, kicker, text, at=0.0, land=None, until=None, tone="cream", layout="split", area=None, z=None):
    fr = Frame(self, layout, area, "ed-kicker", tone)
    _ck, t_in, t_land, t_out = _times(fr, at, land, until, 0.9)
    t_h = min(t_land, t_in + (0.3 if fr.split else 0.06))   # a band card arrives with its words (never empty)
    lines = _lines(text)
    px = fr.fit(min(fr.px(ln, 200) for ln in lines), len(lines) * 1.12, 86)
    inner = (f'<div class="eb-kick" data-fit="{fr.width},14" {box("text", t_in + 0.2, t_out)}>{esc(kicker)}</div><i class="eb-rule"></i>'
             + '<div style="margin-top:20px">' + "".join(_mask("eb-h", ln, px, t_h + 0.15, t_out, fr.width)
                                                         for ln in lines) + "</div>")
    fr.start(t_in, t_out)
    fr.js.hide(".eb-kick", {"clipPath": "inset(0% 100% 0% 0%)"})
    fr.js.ft(".eb-kick", {"clipPath": "inset(0% 100% 0% 0%)"}, {"clipPath": "inset(0% 0% 0% 0%)"}, t_in + 0.04, 0.4,
             "power2.out")
    fr.js.hide(".eb-rule", {"scaleX": 0})
    fr.js.ft(".eb-rule", {"scaleX": 0}, {"scaleX": 1}, t_in + 0.1, 0.6, "expo.inOut")
    fr.rise(".eb-h", t_h, stagger=0.08)
    if t_land > t_h + 0.25:
        fr.js.ft(".eb-blk", {"scale": 1.05}, {"scale": 1}, t_land, 0.45, "elastic.out(1,0.45)")
    fr.end(t_out)
    ev = [sfx(t_in, "whoosh", "colour set"), sfx(t_h, "pop", f"headline {text[:16]}")]
    h = 60 + len(lines) * px * 1.1
    return make("ed-kicker", self, fr.pid, fr.html(inner, h), fr.js, ev, t_in, t_out + 0.25,
                {"times": {"in": t_in, "headline": t_h, "land": t_land, "out": t_out}, "px": px})
