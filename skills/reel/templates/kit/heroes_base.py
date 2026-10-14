"""heroes_base: shared plumbing for the hero library (heroes_*.py): colour sets, the stage a hero sits on, a JS emitter
with per-frame motion blur, word-anchored clocks and the typed parameter contract every hero declares.

A hero is one premium, parameterised moment (a timeline that builds, a chart that drops, a cover that sets) that the
plan compiler and a fast model fill from one spoken line. Each hero:
  - is a Kit method returning a Piece (html + js + sfx), host-agnostic like every kit piece (split Ctx, stylekit TL,
    a dict host), with its own CSS and GSAP tweens (no runtime JS, so kit_*.js stays untouched);
  - declares a CONTRACT (fields with types and limits, the layouts it fits, the shortest window it needs);
  - lands on its word, enters with at least two of blur / scale / offset on a snap or land ease, carries per-frame
    motion blur on fast moves, emits light SFX, and stays inside the safe zone and off the face.
Reel Room's own code.
"""
import json
import math

from rrkit_base import FPS, W, H, Piece, box, esc, fam, mix, q, rgba, sfx  # noqa: F401  (re-exported for heroes_*)

HEROES = {}          # id -> contract (filled by @hero)
SETS = ("cream", "dark", "tan", "accent")
LAYOUTS = ("split", "card", "stage", "full", "overlay", "media")
SERIF_FILES = {"Playfair Display": ("PlayfairDisplay.woff2", "PlayfairDisplay-Italic.woff2")}
MONO = ("JetBrains Mono", "JetBrainsMono.woff2")


# ---------------------------------------------------------------------------------------------- contract registry
def hero(hid, method, fields, fits, layouts, say, what, min_secs=2.0, split_mode="split", needs=()):
    """Declare a hero. fields: {name: (type, opts)}; types: text(max, required), texts(n_min, n_max, max_len),
    anchor, anchors(n_max), num(lo, hi), color, set, bool, enum(choices), media(n_max), secs(lo, hi), source(max).
    fits: plain-language list of styles; layouts: split-engine layouts it can draw in; split_mode: the edl mode the
    split-deck adapter uses for it ('split' = top slot, 'full' = over the full-frame speaker); needs: inputs the
    compiler must supply (e.g. 'sources' for a citation)."""
    def deco(fn):
        HEROES[hid] = {"id": hid, "method": method, "fields": fields, "fits": list(fits), "layouts": list(layouts),
                       "say": list(say), "what": what, "min_secs": float(min_secs), "split_mode": split_mode,
                       "needs": list(needs), "hero": True, "fn": fn}
        return fn
    return deco


def catalog(public=True):
    """The hero catalogue without the callables (for the planner, the compiler prompt and docs)."""
    return {k: {kk: vv for kk, vv in v.items() if kk != "fn"} for k, v in HEROES.items()} if public else HEROES


def register(Kit, COMPONENTS):
    """Attach every hero to the Kit and the planner registry (rrkit calls this once, additively)."""
    for hid, c in HEROES.items():
        setattr(Kit, c["method"], c["fn"])
        COMPONENTS[hid] = {"method": c["method"], "say": c["say"], "what": c["what"], "hero": True,
                           "fits": c["fits"], "layouts": c["layouts"], "min_secs": c["min_secs"]}


# ---------------------------------------------------------------------------------------------- colour sets
def colour_set(kit, name="cream"):
    """Brand-derived colour sets (showcase style shifts): cream paper, warm dark, tan, accent.
    Every value is a mix of brand.json colours, nothing hard-coded about the user."""
    c = kit.brand["colors"]
    bg, ink, acc = c["bg"], c["ink"], c["accent"]
    hl, alert = c.get("highlight", acc), c.get("alert", acc)
    if name == "dark":
        g = mix(ink, bg, 0.9)
        return {"g": g, "g2": mix(ink, bg, 0.82), "ink": bg, "sub": rgba(bg, .62), "acc": mix(acc, "#ffffff", .62),
                "hl": hl, "alert": mix(alert, "#ffffff", .8), "card": mix(ink, bg, 0.8), "line": rgba(bg, .14), "dark": True}
    if name == "tan":
        g = mix(mix(bg, ink, 0.62), mix(hl, alert, 0.6), 0.62)
        return {"g": g, "g2": mix(g, ink, 0.9), "ink": ink, "sub": rgba(ink, .62), "acc": mix(ink, acc, .25),
                "hl": mix(bg, "#ffffff", .5), "alert": mix(alert, ink, .6), "card": mix(bg, g, .55),
                "line": rgba(ink, .16), "dark": False}
    if name == "accent":
        return {"g": acc, "g2": mix(acc, ink, .82), "ink": mix(bg, "#ffffff", .5), "sub": rgba(bg, .7), "acc": hl,
                "hl": hl, "alert": hl, "card": mix(acc, ink, .8), "line": rgba(bg, .18), "dark": True}
    g = mix(bg, "#ffffff", 0.6)
    return {"g": g, "g2": mix(bg, ink, 0.94), "ink": ink, "sub": rgba(ink, .56), "acc": acc, "hl": hl, "alert": alert,
            "card": mix(bg, "#ffffff", 0.25), "line": rgba(ink, .1), "dark": False}


def set_vars(kit, name="cream"):
    """CSS custom properties for a hero root: --h-* (colour set) plus the kit's --k-* font/brand tokens."""
    s = colour_set(kit, name)
    ink = kit.brand["colors"]["ink"]
    d = {"--h-g": s["g"], "--h-g2": s["g2"], "--h-ink": s["ink"], "--h-sub": s["sub"], "--h-acc": s["acc"],
         "--h-hl": s["hl"], "--h-alert": s["alert"], "--h-card": s["card"], "--h-line": s["line"],
         "--h-shadow": f"0 34px 70px {rgba(ink, .26 if s['dark'] else .18)},0 10px 22px {rgba(ink, .12)}",
         "--h-fm": fam(MONO[0], "ui-monospace,Menlo,monospace")}
    return kit.vars("dark" if s["dark"] else "light") + ";" + ";".join(f"{k}:{v}" for k, v in d.items())


def font_css(kit):
    """@font-face for the serif (brand serif, else Playfair Display) and the mono, so a host that only loads the
    brand's display/body/hand faces still draws them (files are copied by ensure_fonts)."""
    serif = kit.brand["fonts"].get("serif", "Playfair Display")
    out = []
    files = SERIF_FILES.get(serif)
    if files:
        out.append(f"@font-face{{font-family:'{serif}';src:url('assets/fonts/{files[0]}') format('woff2');"
                   f"font-weight:400 900;font-style:normal;font-display:block}}")
        out.append(f"@font-face{{font-family:'{serif}';src:url('assets/fonts/{files[1]}') format('woff2');"
                   f"font-weight:400 900;font-style:italic;font-display:block}}")
    out.append(f"@font-face{{font-family:'{MONO[0]}';src:url('assets/fonts/{MONO[1]}') format('woff2');"
               f"font-weight:100 900;font-style:normal;font-display:block}}")
    return "<style data-rrh-fonts>" + "".join(out) + "</style>"


def ensure_fonts(project_dir):
    """Copy the serif + mono files into <project>/assets/fonts (from the Reel Room font cache). Quiet when absent."""
    import os
    import shutil
    src_dirs = [os.path.expanduser("~/.reel-room/cache/fonts")]
    dest = os.path.join(project_dir, "assets", "fonts")
    os.makedirs(dest, exist_ok=True)
    names = [n for pair in SERIF_FILES.values() for n in pair] + [MONO[1]]
    for n in names:
        if os.path.exists(os.path.join(dest, n)):
            continue
        for d in src_dirs:
            if os.path.exists(os.path.join(d, n)):
                shutil.copyfile(os.path.join(d, n), os.path.join(dest, n))
                break


# ---------------------------------------------------------------------------------------------- stage geometry
class Stage:
    """Where a hero draws. layout 'split' = the 1080x960 top panel (the hero paints its colour-set ground over it,
    content in the safe band y 230-930); 'card' / 'stage' = the paper stage above the speaker card; 'full' /
    'overlay' = over the full-frame speaker, content in the band above the head (area) unless the hero takes the
    whole frame itself."""

    def __init__(self, layout="split", area=None):
        self.layout = layout if layout in LAYOUTS else "full"
        y0, y1 = area or ((META_H, 930) if self.layout == "split" else (240, 900))
        self.y0, self.y1 = max(230, int(y0)), min(1460, int(y1))
        if self.layout == "split":
            self.y0, self.y1 = max(self.y0, META_H), min(self.y1, 930)

    @property
    def h(self):
        return self.y1 - self.y0

    def fit(self, w, h, x=None, valign=0.5):
        """(x, y, w, h) of a w x h box inside the band, shrunk to fit; centred unless x is given."""
        h = min(h, self.h)
        bx = round((W - w) / 2) if x is None else x
        by = round(self.y0 + (self.h - h) * valign)
        return bx, by, w, h

    def ground(self, pid, name, kit):
        """Full-panel colour-set ground for the split top slot (nothing readable, no data-box)."""
        if self.layout != "split" or not name:
            return ""
        s = colour_set(kit, name)
        handle = kit.brand.get("handle")
        meta = (f'<div class="rrh-meta"><span>{esc("@" + handle.lstrip("@"))}</span><i></i></div>' if handle else
                '<div class="rrh-meta"><i></i></div>')
        return (f'<div class="rrh-ground" id="{pid}gr" style="background:radial-gradient(120% 90% at 50% 38%,'
                f'{s["g"]} 0%,{s["g"]} 55%,{s["g2"]} 100%)"><div class="rrh-grid"></div></div>{meta}')


META_H = 292        # split panel: an editorial meta row (handle + rule) sits above the content band
GROUND_CSS = (".rrh-ground{position:absolute;left:-60px;top:-60px;width:1200px;height:1080px}"
              ".rrh-grid{position:absolute;inset:0;opacity:.55;background-image:linear-gradient(var(--h-line) 1px,"
              "transparent 1px),linear-gradient(90deg,var(--h-line) 1px,transparent 1px);background-size:72px 72px;"
              "background-position:24px 24px;-webkit-mask-image:radial-gradient(90% 80% at 50% 45%,#000 30%,transparent 100%);"
              "mask-image:radial-gradient(90% 80% at 50% 45%,#000 30%,transparent 100%)}"
              ".rrh-meta{position:absolute;left:60px;right:60px;top:236px;height:30px;display:flex;align-items:center;gap:18px}"
              ".rrh-meta span{font:600 22px/30px var(--h-fm);letter-spacing:.14em;text-transform:uppercase;color:var(--h-sub);"
              "white-space:nowrap}"
              ".rrh-meta i{flex:1;height:2px;background:var(--h-line);position:relative}"
              ".rrh-meta i::after{content:'';position:absolute;right:0;top:-4px;width:34px;height:10px;border-radius:3px;"
              "background:var(--h-acc)}"
              ".rrh{position:absolute;left:0;top:0;width:1080px;height:960px;pointer-events:none;box-sizing:border-box;"
              "font-family:var(--k-fb);color:var(--h-ink);-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;"
              "word-spacing:.06em}"
              ".rrh-edge{position:absolute;left:44px;right:44px;height:2px;background:var(--h-line)}"
              ".rrh-edge i{position:absolute;top:-5px;width:12px;height:12px;border-radius:2px;background:var(--h-acc)}"
              ".rrh *{box-sizing:border-box}.rrh svg{overflow:visible}.rrh.rrh-full{height:1920px}")


# ---------------------------------------------------------------------------------------------- eases (python side)
def ease(name, p):
    """Python twin of the GSAP curves the heroes use (for per-frame keys and motion-blur velocity)."""
    p = min(1.0, max(0.0, p))
    if name in ("expo.out",):
        return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)
    if name in ("power4.out",):
        return 1 - (1 - p) ** 5
    if name in ("power3.out",):
        return 1 - (1 - p) ** 4
    if name in ("power2.out",):
        return 1 - (1 - p) ** 3
    if name in ("power3.in",):
        return p ** 4
    if name in ("power2.in",):
        return p ** 3
    if name in ("power2.inOut", "camera"):
        return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2
    if name in ("power3.inOut", "expo.inOut"):
        return 8 * p ** 4 if p < .5 else 1 - (-2 * p + 2) ** 4 / 2
    if name in ("sine.inOut",):
        return -(math.cos(math.pi * p) - 1) / 2
    return p


def prng(seed):
    s = [(int(seed) & 0xFFFFFFFF) or 1]

    def r():
        s[0] = (s[0] * 1664525 + 1013904223) & 0xFFFFFFFF
        return s[0] / 4294967296
    return r


# ---------------------------------------------------------------------------------------------- JS emitter
class JS:
    """Collects one hero's GSAP lines (run with `tl` in scope). Selectors are scoped to the piece root."""

    def __init__(self, pid):
        self.pid, self.lines, self.defs, self._n = pid, [], [], 0
        self.split = False
        self._hidden = set()

    def ground_in(self, t, dur=0.42):
        """The split ground is the colour-set shift: it is there on the beat's first frame (no flash of the old
        panel), and settles from a slight push so the shift reads as a move, not a pop."""
        if self.split:
            self.ft(f"#{self.pid}gr", {"scale": 1.06}, {"scale": 1}, t, dur + 0.3, "power2.out")

    def s(self, sel):
        if not sel:
            return json.dumps("#" + self.pid)
        if sel.startswith("#"):
            return json.dumps(sel)
        return json.dumps(f"#{self.pid} {sel}")

    def hide(self, sel, props):
        self.lines.append(f"gsap.set({self.s(sel)},{json.dumps(props, separators=(',', ':'))});")

    def ft(self, sel, frm, to, t, dur, ease_="expo.out", stagger=None):
        """fromTo with immediateRender:false on its frame (flat objects only, so QA's ease_lint can read it)."""
        if (frm.get("opacity") == 0 or frm.get("autoAlpha") == 0) and sel not in self._hidden:
            self.hide(sel, frm)                    # an entrance: its from-state holds until its frame
            self._hidden.add(sel)
        to = dict(to, duration=round(dur, 4), ease=ease_, immediateRender=False)
        if stagger:
            to["stagger"] = stagger
        self.lines.append(f"tl.fromTo({self.s(sel)},{json.dumps(frm, separators=(',', ':'))},"
                          f"{json.dumps(to, separators=(',', ':'))},{q(t)});")

    def to(self, sel, vars_, t, dur, ease_="power2.out"):
        v = dict(vars_, duration=round(dur, 4), ease=ease_)
        self.lines.append(f"tl.to({self.s(sel)},{json.dumps(v, separators=(',', ':'))},{q(t)});")

    def set(self, sel, vars_, t):
        self.lines.append(f"tl.set({self.s(sel)},{json.dumps(vars_, separators=(',', ':'))},{q(t)});")

    def life(self, t0, t1):
        """The piece root: hidden at build, shown on t0, gone at t1."""
        self.hide("", {"autoAlpha": 0})
        self.set("", {"autoAlpha": 1}, t0)
        self.set("", {"autoAlpha": 0}, t1)

    def mblur(self, sel, t, dur, dx=0.0, dy=0.0, ease_="expo.out", k=0.42, cap=36.0):
        """Per-frame directional motion blur on `sel` while it travels (dx, dy) px over [t, t+dur] on ease_.
        Keyed one tl.set per frame (seek-safe); the filter is 'none' whenever the blur is under 0.6 px.
        Put it on a wrapper that no other tween gives a CSS filter."""
        self._n += 1
        fid = f"{self.pid}mb{self._n}"
        self.defs.append(f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%" '
                         f'color-interpolation-filters="sRGB"><feGaussianBlur id="{fid}g" in="SourceGraphic" '
                         f'stdDeviation="0 0"/></filter>')
        n = max(1, int(round(dur * FPS)))
        on = False
        for i in range(n):
            a, b = ease(ease_, i / n), ease(ease_, (i + 1) / n)
            bx, by = min(cap, abs(b - a) * abs(dx) * k), min(cap, abs(b - a) * abs(dy) * k)
            tt = t + i / FPS
            if max(bx, by) >= 0.6:
                self.set(f"#{fid}g", {"attr": {"stdDeviation": f"{bx:.1f} {by:.1f}"}}, tt)
                if not on:
                    self.set(sel, {"filter": f"url(#{fid})"}, tt)
                    on = True
            elif on:
                self.set(sel, {"filter": "none"}, tt)
                on = False
        if on:
            self.set(sel, {"filter": "none"}, t + n / FPS)

    def svg_defs(self):
        return (f'<svg width="0" height="0" style="position:absolute"><defs>{"".join(self.defs)}</defs></svg>'
                if self.defs else "")

    def per_frame(self, sel, t0, t1, fn):
        """One tl.set per frame on [t0, t1]: fn(p) -> vars (p = 0..1 linear). For counters, timecodes, flicker."""
        f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
        for f in range(f0, f1 + 1):
            p = (f - f0) / max(1, f1 - f0)
            v = fn(p, f)
            if v is not None:
                self.set(sel, v, f / FPS)


# ---------------------------------------------------------------------------------------------- time
class Clock:
    """Word-anchored times for one hero. Every event searches from the entrance, so anchors may come in any order;
    numbers are seconds after the kit's base; a missing word falls back to t_in + default."""

    def __init__(self, kit, at, lead="visual"):
        self.kit = kit
        self.t_in = kit.cursor()(at, 0.0, lead)

    def at(self, spec, default, lead="visual", floor=None):
        t = self.kit.cursor(start=self.t_in)(spec, default, lead, rel=self.t_in)
        return round(max(t, self.t_in if floor is None else floor), 4)

    def early(self, spec, default, lead="visual"):
        """An anchor that may come BEFORE the entrance word (a set-up line): searched from the kit's base."""
        t = self.kit.cursor()(spec, 0.0, lead, rel=self.t_in + default) if spec is not None else self.t_in + default
        return round(max(0.0, t), 4)

    def end(self, until, need, hold=1.2):
        """Hero end: `until`, else the split beat end, else need + hold; never before need + 0.4 s."""
        t = self.kit.until(until, self.t_in, need + hold - self.t_in, self.kit.cursor(start=self.t_in))
        return round(max(t, need + 0.4), 4)


# ---------------------------------------------------------------------------------------------- html helpers
def root(pid, comp, kit, set_name, inner, stage, full=False, extra_css="", z=None):
    """The hero root: fonts, base CSS, its colour-set vars, ground (split), the inner markup."""
    zs = f"z-index:{z};" if z is not None else ""
    cls = "rrh rrh-full" if full else "rrh"
    return (font_css(kit) + f"<style>{GROUND_CSS}{extra_css}</style>"
            + f'<div class="{cls} rrh-{comp}" id="{pid}" data-hero data-layout-allow-overflow '
              f'style="{zs}{set_vars(kit, set_name)}">{stage.ground(pid, set_name, kit)}{inner}</div>')


def text_px(text, max_w, max_px, k=0.56, lo=40):
    """A font size that fits `text` on one line in max_w (k = average glyph width in em for the face)."""
    n = max(1, len(str(text)))
    return int(max(lo, min(max_px, max_w / (k * n))))


def make(comp, kit, pid, html, js, events, t0, t1, meta):
    return Piece(comp, pid, html, js.lines, sorted(events, key=lambda e: e["t"]), t0, t1, meta)
