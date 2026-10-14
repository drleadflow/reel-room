"""Build context shared by every insert: unique ids, time resolution (seconds / '@word'), tween emitters, box tags."""
import html
import json
import os
import re
import subprocess
import sys

from timeline import Words

FPS = 30
_MOTION = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "motion")
if _MOTION not in sys.path:
    sys.path.insert(0, _MOTION)
from motion import upgrade_ease, WordCursor  # noqa: E402


def snap(t):
    """Timeline time for an event meant to land ON frame N = round(t*FPS): half a frame early, so the frame at N/FPS
    (and every later one) sees it, immune to float/rounding noise. Frame N-1 (a full frame earlier) does not."""
    # never negative: GSAP shifts the WHOLE timeline when a child is placed before 0
    return max(0.0, round((round(t * FPS) - 0.5) / FPS, 5))


def floor5(t):
    """Media data-start/duration: never round up past the frame time."""
    import math
    return math.floor(t * 1e5 + 1e-6) / 1e5


ZERO_KEYS = ("x", "y", "rotation", "rotationX", "rotationY")


def esc(s):
    return html.escape(str(s), quote=True)


class Ctx:
    def __init__(self, brand, words: Words, hook, project_dir):
        self.brand, self.words, self.hook, self.dir = brand, words, hook or {}, project_dir
        self.tw = []
        self.warnings = []
        self.n = 0
        self.track = 10
        self._dur = {}
        self.init = []        # extra gsap.set lines run before the timeline is built
        self.extra_boxes = [] # planned boxes for QA (final states the static measure cannot see)
        self.events = []      # [{t, kind, what}] graphic entrances (sound design + QA switch checks)
        self.card = {"top": 1010, "inset": 28, "radius": 64, "face_y": 1330, "scale": 1.0}
        self.stage_bottom = 1180
        self.head_margin = 24
        self._heads = []      # [(t, head_top, chin, skin_box)] in screen pixels, from the face track
        self._slices = []
        self.cut_marks = set()  # cut times where an insert changes the picture on the cut frame

    # head box (screen pixels) from the per-frame face track mapped through the speaker placement
    def attach_heads(self, placement, track, facepos, segs):
        import layouts as lay
        self._slices = placement
        rows = []
        if track:
            hu, cd = track.get("head_up", 1.1), track.get("chin_down", 0.8)
            for k, v in track["faces"].items():
                t = int(k) / FPS
                pl = next((p for p in placement if p["t0"] - 1e-6 <= t < p["t1"] - 1e-6), None)
                if not pl or not pl.get("visible", True):
                    continue
                skin, head = lay.face_box(pl, v[0], v[1], v[2], hu, cd)
                rows.append((t, head["y"], head["y"] + head["h"], skin))
        else:
            for pl in placement:
                fp = facepos.get(pl["seg"])
                if fp and pl.get("visible", True):
                    skin, head = lay.face_box(pl, fp["cx"], fp["cy"], fp["h"])
                    for t in (pl["t0"], (pl["t0"] + pl["t1"]) / 2, pl["t1"] - 1e-3):
                        rows.append((t, head["y"], head["y"] + head["h"], skin))
        self._heads = sorted(rows, key=lambda r: r[0])

    def _rows(self, t0, t1):
        return [r for r in self._heads if t0 - 0.05 <= r[0] <= t1 + 0.05]

    def head_top(self, t0, t1, default=780):
        r = self._rows(t0, t1)
        return round(min(x[1] for x in r)) if r else default

    def chin(self, t0, t1):
        r = self._rows(t0, t1)
        return round(max(x[2] for x in r)) if r else None

    def cut_change(self, t):
        """An insert changes the picture exactly on this cut frame (B-roll step-in, chart step): compose then does not
        warn about a jump cut there. Register only real picture changes."""
        self.cut_marks.add(round(t, 2))

    def event(self, t, kind, what=""):
        """Register a graphic moment (for sound design + QA). kind: whoosh|pop|click|scribble|flip|thud|tick"""
        self.events.append({"t": round(t, 3), "kind": kind, "what": what})

    # ids / tags
    def uid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def next_track(self):
        self.track += 1
        return self.track

    def warn(self, msg):
        self.warnings.append(msg)
        print("  WARN", msg)

    def box(self, kind, t0, t1, readable=False):
        return f'data-box="{kind}" data-t0="{t0:.3f}" data-t1="{t1:.3f}"' + (' data-readable="1"' if readable else "")

    # time
    def when(self, spec, beat, default=0.0):
        """None -> beat start + default; number -> seconds after beat start; '@word[:n][+/-off]' -> word start."""
        a0 = beat.get("anchor_t0", beat["t0"])
        if spec is None:
            return a0 + default
        if isinstance(spec, (int, float)):
            return a0 + float(spec)
        if str(spec).startswith("#"):  # '#seg' = the first frame of that cut (+/- offset): lands ON the cut
            m = re.match(r"^#([\w-]+)([+-]\d*\.?\d+)?$", str(spec).strip())
            seg = next((x for x in getattr(self, "segs", []) if m and x["id"] == m.group(1)), None)
            if seg is None:
                self.warn(f"cut {spec!r} not found; using +{default}s")
                return a0 + default
            return seg["t0"] + float(m.group(2) or 0)
        m = re.match(r"^@(.+?)(?::(\d+))?(?:([+-]\d*\.?\d+))?$", str(spec).strip())
        if not m:
            self.warn(f"bad time spec {spec!r}")
            return a0 + default
        key = m.group(1) + (f":{m.group(2)}" if m.group(2) else "")
        t = self.words.find(key, a0 - 0.02, beat["t1"])
        if t is None:
            self.warn(f"word {spec!r} not found in beat {beat['id']} ({a0:.2f}-{beat['t1']:.2f}); using +{default}s")
            return a0 + default
        return t + float(m.group(3) or 0)

    def cue(self, spec, beat, after=None, lead="visual", fallback=0.0):
        """Word-anchored time with ORDERED search and a named lead (motion v2): '@word[:n][+off]' searched from `after`
        (the previous cue of the same insert) inside the beat, minus the lead (visual 0.04 s, stamp 0.03, push 0.02,
        type 0.05, none 0): visuals land a frame before the word. A missing word falls back to after + fallback."""
        a0 = beat.get("anchor_t0", beat["t0"]) if after is None else after
        if isinstance(spec, (int, float)):
            return beat.get("anchor_t0", beat["t0"]) + float(spec)
        cur = WordCursor([{"text": x["text"], "start": x["start"], "end": x["end"]} for x in self.words.w], a0 - 0.02, beat["t1"])
        return cur.at(spec, fallback=fallback, lead=lead)

    # tweens
    def enter(self, beat, sel, t, frm, to=None, dur=0.35, ease="power3.out"):
        end = dict(to) if to else {k: (0 if k in ZERO_KEYS else 1) for k in frm}
        ease = upgrade_ease(ease, getattr(self, "motion_cfg", None))
        if t < beat["t0"] - 1e-3:  # beat resumes after a cut-in: show the settled state
            self.tw.append(f"tl.set({json.dumps(sel)},{json.dumps(end)},{snap(beat['t0'])});")
            return
        end.update(duration=dur, ease=ease)
        self.tw.append(f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(end)},{snap(t)});")

    def to(self, sel, t, vars_, dur=0.3, ease="power2.out"):
        v = dict(vars_)
        v.update(duration=dur, ease=ease)
        self.tw.append(f"tl.to({json.dumps(sel)},{json.dumps(v)},{snap(t)});")

    def set(self, sel, t, vars_):
        self.tw.append(f"tl.set({json.dumps(sel)},{json.dumps(vars_)},{snap(t)});")

    # media
    def abs_path(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.dir, rel)

    def media_dur(self, rel):
        if rel in self._dur:
            return self._dur[rel]
        d = None
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  self.abs_path(rel)], capture_output=True, text=True, timeout=20).stdout.strip()
            d = float(out) if out else None
        except Exception:
            d = None
        self._dur[rel] = d
        return d

    def crop_of(self, rel):
        """Detect baked-in black bars on a video: returns (src_w, src_h, x, y, w, h) or None when the frame is clean."""
        key = "crop:" + rel
        if key in self._dur:
            return self._dur[key]
        res = None
        try:
            p = self.abs_path(rel)
            dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                   "-of", "csv=p=0", p], capture_output=True, text=True, timeout=20).stdout.strip().split(",")
            sw, sh = int(dims[0]), int(dims[1])
            out = subprocess.run(["ffmpeg", "-v", "info", "-ss", "1", "-i", p, "-t", "1.5", "-vf", "cropdetect=limit=28:round=2:reset=0",
                                  "-f", "null", "-"], capture_output=True, text=True, timeout=40).stderr
            found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", out)
            if found:
                w, h, x, y = map(int, found[-1])
                if w * h < 0.96 * sw * sh and w > sw * 0.5 and h > sh * 0.5:
                    res = (sw, sh, x, y, w, h)
        except Exception:  # noqa: BLE001
            res = None
        self._dur[key] = res
        return res

    def img_size(self, rel):
        try:
            from PIL import Image
            with Image.open(self.abs_path(rel)) as im:
                return im.size
        except Exception:
            return (1080, 920)

    def check_asset(self, rel):
        if not os.path.exists(self.abs_path(rel)):
            self.warn(f"asset missing: {rel}")
