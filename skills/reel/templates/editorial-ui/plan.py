"""Beat plan for the editorial-ui template: which cut sits on the coloured set and which in the real room, the set
punch-in, the headline behind the head, the UI cards, and the face geometry every layer is placed around.

Config: project.json "editorial" (merged over the template's style.json):
  "editorial": {
    "beats": {
      "<segment id>": {"scene": "set" | "room" | "takeover", "zoom": 1.12,
                       "headlines": [{"at": 0 | "@word[+off]", "text": "BLOOD|WORK" }],   # "|" new line, _x_ italic gold
                       "cards": [{"kind": "status" | "prompt" | "panel" | "cover" | "countdown", "at": ..., ...}]}
    },
    "prompt": {"label": ""}, "set": {...}, "headline": {...}, "subtitle": {...}
  }
Segments without an entry are planned automatically (see auto_beats).
"takeover" (Motion v2): the room opens into a designed page through a circle, the speaker stays in front as a live
cut-out (bake.py writes assets/tko_<seg>.webm), steps aside, and the page carries huge words behind the head, a drawn
chart, a side tracker and a kicker (takeover.py plans and draws it).

All times are cut seconds; every event is turned into a frame number (30 fps) here, so the baked set layer
(bake.py) and the HTML layer (compose.py) switch on exactly the same frames.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STYLEKIT = os.path.join(os.path.dirname(HERE), "stylekit")
for p in (STYLEKIT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import kit  # noqa: E402  (stylekit: project loading, word anchors, html page, render, audio)

FPS = 30
W, H = 1080, 1920
HEAD_UP, BROW_UP, CHIN_DOWN = 1.1, 0.5, 0.8   # in face-detector heights around the detector centre


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_style(pj):
    with open(os.path.join(HERE, "style.json")) as f:
        base = json.load(f)
    return deep_merge(base, pj.get("editorial", {}))


class Plan:
    def __init__(self, project_dir):
        self.proj = kit.Project(project_dir)
        self.dir = self.proj.dir
        self.cfg = load_style(self.proj.pj)
        self.warnings = []
        edl = {e["id"]: e for e in kit.jload(self.proj.p("edl.json"), [])}
        self.segs = []
        for s in self.proj.segments:
            e = edl.get(s["id"], {})
            self.segs.append({"id": s["id"], "f0": s["frame"], "f1": s["frame"] + s["frames"],
                              "t0": s["frame"] / FPS, "t1": (s["frame"] + s["frames"]) / FPS,
                              "edl_zoom": float(e.get("zoom", s.get("zoom", 1.0))), "line": e.get("line", s.get("line", "")),
                              "edl_top": e.get("top")})
        self.frames = self.segs[-1]["f1"]
        self.track = kit.jload(self.proj.p("work", "facetrack.json"), {}) or {}
        beats = self.cfg.get("beats") or {}
        auto = self.auto_beats()
        for s in self.segs:
            b = beats.get(s["id"], auto.get(s["id"], {"scene": "room"}))
            s["scene"] = b.get("scene", "room")
            dz = 1.0 if s["edl_zoom"] > 1.05 else self.cfg["set"]["zoom"]
            s["zoom"] = float(b.get("zoom", dz)) if s["scene"] == "set" else 1.0   # takeover: the cut-out moves instead
            s["beat"] = b
            s["set"] = b.get("set", self.cfg["set"].get("default", "brand"))
        self._geometry()
        self.headlines = self._headlines()
        self.cards = self._cards()
        if not (self.cfg.get("tracker") or {}).get("items") and any(s["scene"] == "takeover" for s in self.segs):
            self.cfg["tracker"] = {**self.auto_tracker(), **(self.cfg.get("tracker") or {})}
        self.subj_xf = {}            # frame -> (scale, dx, dy, ox, oy) of the takeover cut-out (takeover.py)
        if any(s["scene"] == "takeover" for s in self.segs):
            import takeover
            self.takeovers = takeover.plan_all(self)
        else:
            self.takeovers = []

    # ------------------------------------------------------------------ helpers
    def warn(self, m):
        self.warnings.append(m)
        print("  WARN", m)

    def seg(self, sid):
        return next(s for s in self.segs if s["id"] == sid)

    def seg_of_frame(self, f):
        return next((s for s in self.segs if s["f0"] <= f < s["f1"]), self.segs[-1])

    def at(self, spec, s, default=0.0):
        """'@word[:n][+/-off]' inside segment s, or seconds after its start -> frame number (clamped to the segment)."""
        if spec is None:
            t = s["t0"] + default
        elif isinstance(spec, (int, float)):
            t = s["t0"] + float(spec)
        else:
            m = re.match(r"^@(.+?)(?::(\d+))?(?:([+-]\d*\.?\d+))?$", str(spec).strip())
            if not m:
                raise SystemExit(f"bad time {spec!r} in segment {s['id']}")
            key = m.group(1) + (f":{m.group(2)}" if m.group(2) else "")
            w = self.proj.words.find(key, s["t0"] - 0.02, s["t1"])
            if w is None:
                raise SystemExit(f"word {spec!r} not spoken inside segment {s['id']} ({s['t0']:.2f}-{s['t1']:.2f}s)")
            t = w + float(m.group(3) or 0)
        return int(min(max(round(t * FPS), s["f0"]), s["f1"] - 1))

    def word_end_frame(self, spec, s):
        f = self.at(spec, s)
        t = f / FPS
        for w in self.proj.words_raw:
            if abs(float(w["start"]) - t) < 0.5 / FPS:
                return int(round(float(w["end"]) * FPS))
        return f

    # ------------------------------------------------------------------ auto plan
    def auto_beats(self):
        """No config: hook + every numbered point go on the set (headline from the edl insert), the rest stay in the room."""
        out = {}
        hook = self.proj.pj.get("hook", {})
        for i, s in enumerate(self.segs):
            top = s.get("edl_top") or {}
            ins = top.get("insert") if isinstance(top, dict) else None
            args = top.get("args", {}) if isinstance(top, dict) else {}
            if i == 0:
                txt = (hook.get("l1") or "").strip()
                out[s["id"]] = {"scene": "set", "headlines": [{"at": 0, "text": txt or s["line"].split(",")[0][:18].upper()}]}
            elif ins == "number" and self.cfg.get("takeover", {}).get("auto", True):
                # Motion v2: every numbered point opens a takeover page: "No. N" in the serif italic, then the title
                # heavy behind the head, the side tracker filling step N
                n = args.get("n", "")
                title = str(args.get("title", "")).upper()
                at = 0.9                 # the title lands on its first spoken word when he says it in this cut
                for wd in re.findall(r"[a-z0-9']+", title.lower()):
                    if len(wd) > 2 and self.proj.words.find(wd, s["t0"] - 0.02, s["t1"]) is not None:
                        at = "@" + wd
                        break
                out[s["id"]] = {"scene": "takeover", "step": int(n) if str(n).isdigit() else None,
                                "words": [{"at": 0, "text": f"_No. {n}_"}, {"at": at, "text": title}]}
            elif ins == "number":
                out[s["id"]] = {"scene": "set", "headlines": [{"at": 0, "text": f"_No. {args.get('n', '')}_"},
                                                             {"at": 0.9, "text": str(args.get("title", "")).upper()}]}
        return out

    def auto_tracker(self):
        """Tracker items from the edl number inserts (titles in order); count from the highest number or the hook."""
        items, top = {}, 0
        for s in self.segs:
            top_ = s.get("edl_top") or {}
            if isinstance(top_, dict) and top_.get("insert") == "number":
                a = top_.get("args", {})
                if str(a.get("n", "")).isdigit():
                    items[int(a["n"])] = str(a.get("title", "")).strip().capitalize()
                    top = max(top, int(a["n"]))
        m = re.search(r"\b(\d{1,2})\b", " ".join(str(v) for v in (self.proj.pj.get("hook") or {}).values()))
        count = max(top, int(m.group(1)) if m and int(m.group(1)) <= 12 else 0)
        return {"items": [items.get(i, "") for i in range(1, top + 1)], "count": count}

    # ------------------------------------------------------------------ geometry
    def _seg_median(self, s):
        if "_med" not in s:
            faces = self.track.get("faces", {})
            pts = [faces[str(g)] for g in range(s["f0"], s["f1"]) if str(g) in faces and faces[str(g)][3]]
            s["_med"] = tuple(sorted(p[i] for p in pts)[len(pts) // 2] for i in range(3)) if pts else None
        return s["_med"]

    def _ok(self, s, v):
        """Reject detector jumps: a sample whose centre is more than 0.6 face heights from the cut's median."""
        m = self._seg_median(s)
        return m is None or (abs(v[0] - m[0]) < 0.6 * m[2] and abs(v[1] - m[1]) < 0.6 * m[2])

    def face_at(self, f):
        """Face (cx, cy, h) in aroll pixels at frame f from the per-frame track (nearest good sample in the same cut)."""
        faces = self.track.get("faces", {})
        s = self.seg_of_frame(f)
        best = None
        for k in range(0, 24):
            for g in (f - k, f + k):
                if s["f0"] <= g < s["f1"] and str(g) in faces and self._ok(s, faces[str(g)]):
                    best = faces[str(g)]
                    break
            if best:
                break
        if not best:
            fp = kit.jload(self.proj.p("work", "facepos.json"), {}).get(s["id"])
            if not fp:
                return None
            return fp["cx"], fp["cy"], fp["h"]
        return best[0], best[1], best[2]

    def map_pt(self, s, x, y, f=None):
        z, (ax, ay) = s["zoom"], s["anchor"]
        x, y = ax + (x - ax) * z, ay + (y - ay) * z
        xf = self.subj_xf.get(f) if f is not None and getattr(self, "subj_xf", None) else None
        if xf:                       # takeover: the cut-out is scaled about (ox, oy) and shifted
            k, dx, dy, ox, oy = xf
            x, y = ox + (x - ox) * k + dx, oy + (y - oy) * k + dy
        return x, y

    def face_box(self, f, pad=0.0):
        """Screen-space face box (brow-to-chin skin, ear to ear) at frame f, after the set punch-in."""
        fc = self.face_at(f)
        if not fc:
            return None
        s = self.seg_of_frame(f)
        cx, cy, h = fc
        x0, y0 = self.map_pt(s, cx - 0.62 * h, cy - BROW_UP * h, f)
        x1, y1 = self.map_pt(s, cx + 0.62 * h, cy + CHIN_DOWN * h, f)
        return [x0 - pad, y0 - pad, x1 + pad, y1 + pad]

    def head_box(self, f):
        fc = self.face_at(f)
        if not fc:
            return None
        s = self.seg_of_frame(f)
        cx, cy, h = fc
        x0, y0 = self.map_pt(s, cx - 0.75 * h, cy - HEAD_UP * h, f)
        x1, y1 = self.map_pt(s, cx + 0.75 * h, cy + CHIN_DOWN * h, f)
        return [x0, y0, x1, y1]

    def _geometry(self):
        for s in self.segs:
            fr = [f for f in range(s["f0"], s["f1"]) if str(f) in self.track.get("faces", {})]
            fcs = [self.face_at(f) for f in (fr or [s["f0"]])]
            fcs = [x for x in fcs if x]
            if not fcs:
                self.warn(f"no face for segment {s['id']}; assuming centre")
                fcs = [(540, 980, 190)]
            med = sorted(fcs, key=lambda x: x[1])[len(fcs) // 2]
            s["anchor"] = (float(med[0]), float(med[1]))
            boxes = [self.face_box(f) for f in (fr or [s["f0"]])]
            heads = [self.head_box(f) for f in (fr or [s["f0"]])]
            boxes = [b for b in boxes if b] or [[440, 880, 640, 1150]]
            heads = [b for b in heads if b] or [[420, 760, 660, 1150]]
            s["brow"] = min(b[1] for b in boxes)          # highest brow line on screen in this cut
            s["chin"] = max(b[3] for b in boxes)          # lowest chin
            s["head_top"] = min(b[1] for b in heads)
            s["head_x"] = (min(b[0] for b in heads), max(b[2] for b in heads))
            # under the chin with the QA face pad (18% of the face height) + a margin
            chin_clear = s["chin"] + 0.2 * (s["chin"] - s["brow"]) + 12
            s["sub_top"] = round(min(max(self.cfg["subtitle"]["min_top"], chin_clear), self.cfg["subtitle"]["max_top"]))

    def sub_top_for(self, f0, f1):
        """Subtitle top for frames f0..f1: under the lowest chin in that window (+ QA face pad), within safe limits."""
        sc = self.cfg["subtitle"]
        boxes = [self.face_box(f) for f in range(f0, max(f0 + 1, f1))]
        boxes = [b for b in boxes if b]
        if not boxes:
            return sc["min_top"]
        clear = max(b[3] + 0.2 * (b[3] - b[1]) + 12 for b in boxes)
        if clear <= sc["max_top"]:
            return round(max(sc["min_top"], clear)), False
        # chin very low (leaning in): compact pill, pushed to the last safe row (bottom edge <= 1470)
        top = round(min(clear, 1470 - sc.get("compact_h", 64)))
        if clear > top:
            self.warn(f"frames {f0}-{f1}: chin low, compact subtitle at {top} (wants {clear:.0f})")
        return top, True

    # ------------------------------------------------------------------ headlines
    def _headlines(self):
        out = []
        hc = self.cfg["headline"]
        for s in self.segs:
            if s["scene"] != "set":
                continue
            hl = s["beat"].get("headlines", [])
            starts = [self.at(h.get("at", 0), s) for h in hl]
            key = s["set"]
            for i, h in enumerate(hl):
                key = h.get("set", key)
                f0 = starts[i]
                f1 = starts[i + 1] if i + 1 < len(hl) else s["f1"]
                if f1 <= f0:
                    continue
                # letters sit above the head; their lower part tucks behind the cap (overlap = share of cap height)
                bottom = s["head_top"] + hc["overlap"] * (s["brow"] - s["head_top"])
                out.append({"id": f"h{len(out)}", "seg": s["id"], "f0": f0, "f1": f1, "text": h["text"],
                            "static": f0 == 0, "bottom": round(h.get("bottom", bottom)), "cfg": h, "set": key})
        return out

    def set_key_at(self, f):
        """Palette key of the set colour on frame f (segment colour, switched by a headline's own "set")."""
        s = self.seg_of_frame(f)
        key = s.get("set", "brand")
        for h in self.headlines:
            if h["seg"] == s["id"] and h["f0"] <= f:
                key = h["set"]
        return key

    # ------------------------------------------------------------------ cards
    def _cards(self):
        out = []
        for s in self.segs:
            for c in s["beat"].get("cards", []):
                c = dict(c)
                c["seg"] = s["id"]
                c["f0"] = self.at(c.get("at", 0), s)
                c["f1"] = self.at(c["until"], s) if c.get("until") is not None else s["f1"]
                for k in ("send", "done"):
                    if c.get(k) is not None:
                        c[k + "_f"] = self.at(c[k], s)
                if c.get("text_at") is not None:
                    c["text_f"] = self.at(c["text_at"], s)
                for r in c.get("rows", []):
                    r["f"] = self.at(r.get("at", 0), s)
                c["id"] = f"k{len(out)}"
                out.append(c)
        return out

    # ------------------------------------------------------------------ export
    def summary(self):
        return {"frames": self.frames,
                "segments": [{k: s[k] for k in ("id", "f0", "f1", "scene", "set", "zoom", "anchor", "brow", "chin",
                                                 "head_top", "sub_top")} for s in self.segs],
                "takeovers": [{k: v for k, v in t.items() if k in ("seg", "f0", "f1", "reveal", "slide", "page", "step", "webm")}
                              for t in getattr(self, "takeovers", [])],
                "headlines": [{k: h[k] for k in ("id", "seg", "f0", "f1", "text", "static", "bottom", "set")} for h in self.headlines],
                "cards": [{k: v for k, v in c.items() if k not in ("rows",)} for c in self.cards],
                "warnings": self.warnings}


if __name__ == "__main__":
    pl = Plan(sys.argv[1])
    print(json.dumps(pl.summary(), indent=1, default=str))
