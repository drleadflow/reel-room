"""rrkit_base: the kit's core (Kit, Piece, time anchors, brand tokens, placement). Import rrkit, not this."""
import html as _html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(os.path.dirname(HERE))
MOTION_DIR = os.path.join(SK, "engine", "motion")
if MOTION_DIR not in sys.path:
    sys.path.insert(0, MOTION_DIR)
from motion import WordCursor  # noqa: E402

FPS = 30
W, H = 1080, 1920
SAFE = {"top": 220, "bottom": 1470, "side": 35, "right_x": 980, "right_from": 1155}
JS_FILES = ("kit_core.js", "kit_ui.js", "kit_fx.js", "kit_pip.js")
CSS_FILE = "kit.css"
LEAD = WordCursor.LEAD
ANCHOR = re.compile(r"^@([^:^+\s]+?)(?::(\d+))?(\^)?([+-]\d*\.?\d+)?$")
# kit event kind -> the split mixer's insert kinds (engine/motion/mixer.py INSERT_SOUND) and stylekit sfx.py names
SOUND_OF = {"pop": "pop", "tick": "tick", "click": "click", "whoosh": "whoosh_soft", "stamp": "stamp",
            "impact": "impact", "flip": "swish", "type": "tick"}
STYLEKIT_SOUND = {"pop": "pop", "tick": "pop_hi", "click": "click", "whoosh": "swish", "stamp": "thump",
                  "impact": "thump", "flip": "swish", "type": "click"}

DEFAULT_BRAND = {"colors": {"bg": "#F6F2EE", "ink": "#1D1214", "accent": "#7A1E2E", "accent2": "#F3E7E4",
                            "highlight": "#D9B45A", "alert": "#A3243A"},
                 "fonts": {"display": "Inter Tight", "body": "Inter", "hand": "Caveat", "serif": "Playfair Display"}}


def esc(s):
    return _html.escape(str(s), quote=True)


def q(t):
    """Timeline time that lands ON frame round(t*30): half a frame early (same rule as RRM.q / the engine snap)."""
    return max(0.0, round((round(t * FPS + 1e-3) - 0.5) / FPS, 5))


def fr(t):
    """Seconds rounded onto the frame grid (for comparisons and data attributes)."""
    return round(round(t * FPS) / FPS, 4)


def _hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def rgba(c, a):
    r, g, b = _hex(c)
    return f"rgba({r},{g},{b},{a})"


def mix(c1, c2, k):
    """k of c1 + (1-k) of c2, as hex (no color-mix() at render time)."""
    a, b = _hex(c1), _hex(c2)
    return "#" + "".join(f"{round(x * k + y * (1 - k)):02x}" for x, y in zip(a, b))


def fam(name, fallback="system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"):
    return f"'{name}',{fallback}"


# ---------------------------------------------------------------------------------------------- pieces
class Piece:
    """One kit component instance: html (markup with data-box tags), js (lines run with `tl` in scope),
    sfx (events), t0/t1 (on-screen window), meta (resolved times, for QA and docs)."""

    def __init__(self, comp, pid, html, js, sfx, t0, t1, meta=None):
        self.comp, self.id, self.html, self.js, self.sfx = comp, pid, html, js, sfx
        self.t0, self.t1, self.meta = t0, t1, meta or {}

    def events(self, level="light"):
        """SFX events at a level: 'off' none, 'light' the hero moments, 'full' everything."""
        if level == "off":
            return []
        keep = ("light",) if level == "light" else ("light", "full")
        return [e for e in self.sfx if e["level"] in keep]

    def __repr__(self):
        return f"<Piece {self.comp} #{self.id} {self.t0:.2f}-{self.t1:.2f}s, {len(self.sfx)} sfx>"


class Kit:
    """Builds pieces with one brand and one word list. base: what plain numbers are relative to (a split beat start;
    0 for full-frame styles, where numbers are cut seconds). end: words after this are not searched."""

    def __init__(self, brand=None, words=None, base=0.0, end=None, prefix="k", total=None):
        b = json.loads(json.dumps(DEFAULT_BRAND))
        for key, v in (brand or {}).items():
            if isinstance(v, dict) and isinstance(b.get(key), dict):
                b[key].update(v)
            else:
                b[key] = v
        self.brand = b
        self.words = [{"text": w["text"], "start": float(w["start"]), "end": float(w["end"])} for w in (words or [])]
        self.base, self.end, self.prefix, self.total = float(base), end, prefix, total
        self._n = 0

    # ---- construction helpers for the two engines
    @classmethod
    def for_split(cls, cx, beat):
        """Split engine: numbers are seconds after the beat start, anchors search inside the beat."""
        k = cls(cx.brand, cx.words.w, base=beat.get("anchor_t0", beat["t0"]), end=beat["t1"], prefix="k")
        k._uid = cx.uid
        k._track = getattr(cx, "next_track", None)
        k.default_until = beat["t1"]
        return k

    @classmethod
    def for_stylekit(cls, proj):
        """Full-frame styles (stylekit Project): numbers are cut seconds."""
        k = cls(proj.brand, proj.words_raw, base=0.0, prefix="k")
        return k

    def uid(self, p):
        if getattr(self, "_uid", None):
            return self._uid(f"rk{p}")
        self._n += 1
        return f"{self.prefix}{p}{self._n}"

    def track(self, default=40):
        if getattr(self, "_track", None):
            return self._track()
        self._n += 1
        return default + self._n

    # ---- time
    def cursor(self, start=None):
        """Ordered anchor resolver for one piece: each call searches from the previous anchor."""
        state = {"pos": self.base if start is None else start}

        def at(spec, default=0.0, lead="visual", rel=None):
            if spec is None:
                t = (state["pos"] if rel is None else rel) + default
                state["pos"] = max(state["pos"], t)
                return round(t, 4)
            if isinstance(spec, (int, float)):
                t = self.base + float(spec)
                state["pos"] = max(state["pos"], t)
                return round(t, 4)
            m = ANCHOR.match(str(spec).strip())
            if not m:
                raise ValueError(f"kit: bad time spec {spec!r} (use seconds or '@word[:n][^][+/-s]')")
            found = self._find(m.group(1), int(m.group(2) or 1), state["pos"] - 0.02)
            if found is None:
                fb = (state["pos"] if rel is None else rel) + default
                print(f"  WARN kit: word {spec!r} not found after {state['pos']:.2f}s; using {fb:.2f}s")
                state["pos"] = fb
                return round(fb, 4)
            off = float(m.group(4) or 0)
            if m.group(3):                      # '^': the word's end, no lead
                state["pos"] = found[1]
                return round(found[1] + off, 4)
            state["pos"] = found[0] + 0.03      # the next anchor searches strictly after this word
            return round(max(0.0, found[0] + off - LEAD.get(lead, 0.0)), 4)
        return at

    def _find(self, word, occ, after):
        want = _norm(word)
        for exact in (True, False):
            seen = 0
            for w in self.words:
                if w["start"] < after or (self.end is not None and w["start"] >= self.end):
                    continue
                n = _norm(w["text"])
                if n == want or (not exact and n.startswith(want)):
                    seen += 1
                    if seen == occ:
                        return (w["start"], w["end"])
        return None

    def until(self, spec, t_in, default_hold, cur):
        """End of a piece: anchor/number, else the split beat end, else t_in + default_hold."""
        if spec is not None:
            return cur(spec, default_hold, lead="none")
        if getattr(self, "default_until", None):
            return self.default_until
        return t_in + default_hold

    # ---- brand tokens
    def vars(self, theme="light", tone=None):
        c, f = self.brand["colors"], self.brand["fonts"]
        ink, bg = c["ink"], c["bg"]
        paper = mix(bg, "#ffffff", 0.35)
        if theme == "dark":
            surf, on, sub = mix(ink, "#000000", 0.92), bg, rgba(bg, .62)
            faint, line = rgba(bg, .16), rgba(bg, .12)
        else:
            surf, on, sub = paper, ink, rgba(ink, .55)
            faint, line = rgba(ink, .10), rgba(ink, .09)
        acc = c.get("accent", "#7A1E2E")
        d = {"--k-bg": bg, "--k-ink": ink, "--k-paper": paper, "--k-acc": acc, "--k-acc2": c.get("accent2", mix(acc, bg, .12)),
             "--k-hl": c.get("highlight", acc), "--k-alert": c.get("alert", acc), "--k-surf": surf, "--k-on": on,
             "--k-sub": sub, "--k-faint": faint, "--k-line": line, "--k-acc-soft": rgba(acc, .14),
             "--k-acc-glow": rgba(acc, .38), "--k-onacc": mix(bg, "#ffffff", .5),
             "--k-shadow": (f"0 34px 64px {rgba(ink, .20)},0 12px 24px {rgba(ink, .12)},0 2px 5px {rgba(ink, .10)},"
                            f"inset 0 0 0 1.5px {rgba('#ffffff', .55 if theme != 'dark' else .06)}"),
             "--k-shadow-s": f"0 14px 28px {rgba(ink, .18)},0 3px 8px {rgba(ink, .12)}",
             "--k-fd": fam(f.get("display", "Inter Tight")), "--k-fb": fam(f.get("body", "Inter")),
             "--k-fh": fam(f.get("hand", "Caveat"), "cursive"), "--k-fs": fam(f.get("serif", "Playfair Display"), "serif")}
        return ";".join(f"{k}:{v}" for k, v in d.items())

    def color(self, name):
        """'accent' | 'ink' | 'light' | 'highlight' | 'alert' | '#hex' -> hex."""
        c = self.brand["colors"]
        table = {"accent": c["accent"], "ink": c["ink"], "light": mix(c["bg"], "#ffffff", .3), "bg": c["bg"],
                 "highlight": c.get("highlight", c["accent"]), "hl": c.get("highlight", c["accent"]),
                 "alert": c.get("alert", c["accent"])}
        return table.get(name, name)

    def _piece(self, comp, pid, html, call, cfg, sfx, t0, t1, meta=None):
        js = [f"RRK.{call}(tl,{json.dumps('#' + pid)},{json.dumps(cfg, separators=(',', ':'))});"]
        return Piece(comp, pid, html, js, sorted(sfx, key=lambda e: e["t"]), t0, t1, meta)


def _norm(t):
    return re.sub(r"[^\w'%$-]+", "", str(t).lower().replace("’", "'")).strip("-")


def sfx(t, kind, what, level="light"):
    return {"t": round(t, 3), "kind": kind, "sound": SOUND_OF.get(kind), "what": what, "level": level}


def box(kind, t0, t1, readable=True):
    """QA tag. 'text' is measured tight (a Range over its contents); use 'glyph' (element rect, clipped) for anything
    whose contents overflow a clip, like odometer drums or rolling numbers."""
    return f'data-box="{kind}" data-t0="{t0:.3f}" data-t1="{t1:.3f}"' + (' data-readable="1"' if readable else "")


def place(pos, w, h, x=None, y=None):
    """Named spots (frame px) that keep a piece inside the Reels safe zone and off the face of a centred speaker.
    top: the band above the head; center: mid frame (cards over a B-roll); lower: above the captions;
    left/right: side columns for HUDs."""
    spots = {"top": ((W - w) / 2, 250), "upper": ((W - w) / 2, 330), "center": ((W - w) / 2, (H - h) / 2 - 60),
             "lower": ((W - w) / 2, 1130), "left": (60, 280), "right": (W - 100 - w, 280)}
    px, py = spots.get(pos or "top", spots["top"])
    return round(px if x is None else x), round(py if y is None else y)


