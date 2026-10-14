"""motion.py: Reel Room Motion v2, the engine-level motion system shared by every style.

The planner turns a cut list, the words and the graphic events of a composition into:
  - a CAMERA RIG on the speaker layer (#mvCam, wraps only the speaker <video>): settle on every visible cut, a slow push
    through each shot, a punch on emphasis words, WIDE/CLOSE reframes on phrase starts that would otherwise sit still,
    optional handheld drift; overscan-covered so a move never shows a frame edge
  - TRANSITIONS on picture cuts (#mvT, wraps the whole picture, captions stay outside): whip, zoom, push, drop, iris,
    flash, smash, rack; budgeted per level
  - an EVENT LOG (time, kind, sound) for the SFX mixer and the QA gates
  - kinetic caption kinds (rise / stamp / grow)
Everything is keyed per frame (RRM.keys in motion.js), so it is deterministic and seek-safe, and QA can recompute
the exact camera transform on any frame (work/motion_plan.json).

Config (project.json "motion", every key optional; per-beat overrides in edl segments or storyboard beats "motion"):
  {"level": "simple" | "polished" (default) | "showreel",
   "sfx": "off" | "light" (default) | "full",
   "grain": false, "vignette": null (level default), "handheld": null (level default),
   "transitions": "auto" | "off" | "every-cut" | <max per 10 s> | {"per10s": 3, "moves": ["whip", "push"]},
   "captions": "auto" | "plain" | "kinetic"}
  edl segment "motion": {"transition": "whip" | "none", "camera": "still" | "close" | "wide" | "push" | "punch",
                         "punch": "@word", "level": "simple", "frame": "close" | "wide"}
  ("frame" with "still": a held framing switch on the cut, nothing else moves in that shot)

The transition key tables, the out/in frame easing and cover() are adapted from reel-kit
(fx/camera-transitions/fx.js), Copyright (c) 2026 Justyn Berkovits, MIT License (THIRD_PARTY_NOTICES.md).
"""
import json
import math
import os
import re
import shutil
import zlib

FPS = 30
W, H = 1080, 1920
HERE = os.path.dirname(os.path.abspath(__file__))
JS_FILE = os.path.join(HERE, "motion.js")
ASSET_NAME = "rrm-motion.js"
T_ORIGIN = (540, 860)       # transition wrapper origin (a little above centre: where the eye sits)

# ---------------------------------------------------------------------------------------------- levels
LEVELS = {
    # cuts + captions + a settle on every cut. At most one graphic per idea (a planner rule, see motion.md).
    "simple": {
        "settle": 1.03, "push": 0.0, "punch": 0.0, "punch_gap": 99, "reframe": 0.0, "fill_gap": None, "filler_gap": 99,
        "handheld": False, "vignette": 0.0, "transitions": "off", "moves": [], "captions": "plain",
        "strength": 0.0, "upgrade_eases": False,
        "targets": {"still_max": None, "active_min": None, "motion_min": None, "events_per_s": None,
                    "hero_min_w": None, "per10s": 0},
    },
    # the full system with density targets: a teaching reel that never sits still, never busy
    "polished": {
        "settle": 1.045, "push": 0.025, "punch": 1.06, "punch_gap": 2.4, "reframe": 1.08, "fill_gap": 1.05, "filler_gap": 1.2,
        "handheld": False, "vignette": 0.16, "transitions": "auto", "moves": ["whip", "zoom", "push", "iris"],
        "captions": "kinetic", "strength": 0.85, "upgrade_eases": True,
        "targets": {"still_max": 1.2, "active_min": 55.0, "motion_min": 4.5, "events_per_s": 1.2,
                    "hero_min_w": 0.6, "per10s": 3.4},
    },
    # "act as a world-class motion designer, show off": a distinct move on every cut, max density, still on brand
    "showreel": {
        "settle": 1.06, "push": 0.04, "punch": 1.1, "punch_gap": 1.3, "reframe": 1.1, "fill_gap": 0.7, "filler_gap": 0.75,
        "handheld": True, "vignette": 0.2, "transitions": "every-cut",
        "moves": ["whip", "zoom", "iris", "drop", "smash", "push", "flash", "rack"],
        "captions": "kinetic", "strength": 1.0, "upgrade_eases": True,
        "targets": {"still_max": 0.8, "active_min": 70.0, "motion_min": 6.0, "events_per_s": 2.0,
                    "hero_min_w": 0.6, "per10s": 30},
    },
}
DEFAULT = {"level": "polished", "sfx": "light", "grain": False, "vignette": None, "handheld": None,
           "transitions": "auto", "captions": "auto"}

# plain-language names a non-expert can say (motion.md has the full phrasebook)
VOCAB = {
    "whip": "whip pan with motion blur", "zoom": "zoom through", "push": "push in on the new shot",
    "drop": "drop down", "iris": "circle reveal from a point", "flash": "white flash", "smash": "smash cut",
    "rack": "rack focus", "settle": "settle on the cut", "punch": "punch in", "reframe": "wide/close switch",
    "drift": "handheld drift",
}
SOUND = {"whip": "whoosh", "zoom": "whoosh_deep", "push": "whoosh_soft", "drop": "whoosh_deep", "iris": "swish",
         "flash": "shutter", "smash": "impact", "rack": None}


def config(pj, override=None):
    """project.json -> resolved motion config (level defaults + project keys)."""
    raw = dict(DEFAULT)
    raw.update((pj or {}).get("motion") or {})
    raw.update(override or {})
    lvl = raw["level"] if raw["level"] in LEVELS else "polished"
    cfg = json.loads(json.dumps(LEVELS[lvl]))
    cfg["level"] = lvl
    cfg["sfx"] = raw["sfx"] if raw["sfx"] in ("off", "light", "full") else "light"
    cfg["grain"] = bool(raw.get("grain"))
    if raw.get("vignette") is not None:
        cfg["vignette"] = float(raw["vignette"])
    if raw.get("handheld") is not None:
        cfg["handheld"] = bool(raw["handheld"])
    if raw.get("captions") in ("plain", "kinetic"):
        cfg["captions"] = raw["captions"]
    tr = raw.get("transitions", "auto")
    if isinstance(tr, dict):
        cfg["per10s"] = float(tr.get("per10s", cfg["targets"]["per10s"]))
        if tr.get("moves"):
            cfg["moves"] = [m for m in tr["moves"] if m in MOVES]
        cfg["transitions"] = "auto"
    elif isinstance(tr, (int, float)):
        cfg["per10s"], cfg["transitions"] = float(tr), ("off" if tr <= 0 else "auto")
    elif tr in ("off", "every-cut"):
        cfg["transitions"] = tr
        cfg["per10s"] = 0 if tr == "off" else 30
    if "per10s" not in cfg:
        cfg["per10s"] = cfg["targets"]["per10s"]
    if cfg["transitions"] != "off" and not cfg["moves"]:
        cfg["moves"] = ["whip", "push"]
    cfg["parallax"] = [p for p in (raw.get("parallax") or []) if isinstance(p, dict) and p.get("sel")]
    if ((pj or {}).get("motion") or {}).get("still_max") is not None:
        cfg["targets"]["still_max"] = float(pj["motion"]["still_max"])
    cfg["explicit"] = sorted(k for k in (((pj or {}).get("motion") or {}) if isinstance((pj or {}).get("motion"), dict) else {})
                             if k in ("handheld", "captions", "transitions", "still_max", "vignette"))
    return cfg


# per-beat levels: what a segment's own "motion": {"level": ...} changes for its span
LEVEL_KEYS = ("settle", "push", "punch", "punch_gap", "reframe", "fill_gap", "filler_gap", "handheld", "transitions",
              "moves", "captions", "strength", "upgrade_eases", "targets")


def for_level(cfg, lvl):
    """The reel config with one level's motion swapped in (a beat's own level). Project-wide explicit choices
    (handheld, captions, transitions, still_max) still win, except that simple stays exempt from the dead-frame gate."""
    if lvl not in LEVELS or lvl == cfg.get("level"):
        return cfg
    c = dict(cfg)
    L = json.loads(json.dumps(LEVELS[lvl]))
    ex = set(cfg.get("explicit", []))
    for k in LEVEL_KEYS:
        if k in ("handheld", "captions") and k in ex:
            continue
        if k in ("transitions", "moves") and "transitions" in ex:
            continue
        c[k] = L[k]
    if "transitions" not in ex:
        c["per10s"] = 0 if L["transitions"] == "off" else (30 if L["transitions"] == "every-cut" else L["targets"]["per10s"])
    if "still_max" in ex and lvl != "simple":
        c["targets"]["still_max"] = cfg["targets"]["still_max"]
    c["level"] = lvl
    return c


def seg_level(ov, cfg):
    lvl = (ov or {}).get("level")
    return lvl if lvl in LEVELS else cfg["level"]


def ov_camera(ov):
    """The camera override a person asked for. A camera key that rounds.py derived from the beat's level
    (listed in from_level) is dropped: the level itself already says it."""
    ov = ov or {}
    cam = ov.get("camera")
    return None if cam and "camera" in (ov.get("from_level") or []) else cam


def level_spans(shots, cfg, total):
    """[[t0, t1, level], ...] covering the reel (QA uses it to judge each span by its own targets)."""
    out = []
    for sh in sorted(shots, key=lambda x: x["t0"]):
        lvl = seg_level(sh.get("override"), cfg)
        if out and out[-1][2] == lvl and abs(out[-1][1] - sh["t0"]) < 1e-3:
            out[-1][1] = round(sh["t1"], 3)
        else:
            out.append([round(sh["t0"], 3), round(sh["t1"], 3), lvl])
    if not out:
        out = [[0.0, round(total, 3), cfg["level"]]]
    return out


def level_at(plan_, t):
    for a, b, lvl in (plan_ or {}).get("levels", []):
        if a - 1e-3 <= t < b:
            return lvl
    return (plan_ or {}).get("level", "polished")


# ---------------------------------------------------------------------------------------------- eases
UPGRADE = {"power1.out": "expo.out", "power2.out": "expo.out", "power3.out": "expo.out", "sine.out": "expo.out",
           "power1.in": "expo.out", "power2.in": "expo.out", "power3.in": "expo.out", "power4.in": "expo.out",
           "expo.in": "expo.out", "sine.in": "expo.out", "none": "expo.out", "linear": "expo.out"}
BAD_ENTRANCE = re.compile(r"^(none|linear|(power\d|sine|expo|circ|quad|cubic|quart|quint)\.in)$")


def upgrade_ease(ease, cfg):
    """Entrance vocabulary swap at polished/showreel: plain power eases become the snap (expo.out); an entrance on a
    linear or ease-in curve (it would crawl in) also becomes snap. Overshoot (back) and elastic stay."""
    if not cfg or not cfg.get("upgrade_eases") or not isinstance(ease, str):
        return ease
    return UPGRADE.get(ease.strip(), ease)


# ---------------------------------------------------------------------------------------------- words
class WordCursor:
    """Word-anchored timing with ordered search and named leads (the reel-kit wordAt idea on '@word' anchors).
    cur = WordCursor(words, start); t = cur.at("@tolerance", fallback=+0.8, lead="visual")"""
    LEAD = {"visual": 0.04, "stamp": 0.03, "push": 0.02, "type": 0.05, "none": 0.0}

    def __init__(self, words, start=0.0, end=None):
        self.w = [(float(x["start"]), float(x["end"]), _norm(x["text"])) for x in words]
        self.pos, self.end = start, end

    def at(self, spec, fallback=None, lead="visual"):
        m = re.match(r"^@?(.+?)(?::(\d+))?([+-]\d*\.?\d+)?$", str(spec).strip())
        want, occ, off = _norm(m.group(1)), int(m.group(2) or 1), float(m.group(3) or 0)
        t, seen = None, 0
        for exact in (True, False):
            seen = 0
            for s, _e, n in self.w:
                if s < self.pos - 0.001 or (self.end is not None and s >= self.end):
                    continue
                if n == want or (not exact and n.startswith(want)):
                    seen += 1
                    if seen == occ:
                        t = s
                        break
            if t is not None:
                break
        if t is None:
            t = self.pos + (fallback or 0.0)
        self.pos = t + 0.01      # the next cue searches strictly after this word
        return max(0.0, t + off - self.LEAD.get(lead, 0.0))


def _norm(t):
    return re.sub(r"[^\w'%$-]+", "", str(t).lower().replace("’", "'")).strip("-")


# ---------------------------------------------------------------------------------------------- transitions
# frames out (before the cut) / in (from the cut), peaks: s scale, x/y px, r deg, bx/by motion blur px.
# whip/zoom/push/drop values adapted from reel-kit camera-transitions (MIT); iris/flash/smash/rack are Reel Room's.
MOVES = {
    "whip": {"out": 4, "inn": 6, "peakOut": {"s": 1.36, "x": -170, "bx": 46}, "peakIn": {"s": 1.36, "x": 170, "bx": 46}},
    "zoom": {"out": 4, "inn": 6, "peakOut": {"s": 1.6, "bx": 14, "by": 14}, "peakIn": {"s": 1.5, "bx": 12, "by": 12}},
    "push": {"out": 0, "inn": 5, "peakIn": {"s": 1.07}},
    "drop": {"out": 4, "inn": 5, "peakOut": {"s": 1.24, "y": 150, "by": 40}, "peakIn": {"s": 1.24, "y": -170, "by": 40}},
    "iris": {"out": 5, "inn": 8},
    "flash": {"out": 0, "inn": 6},
    "smash": {"out": 0, "inn": 5, "peakIn": {"s": 1.22}},
    "rack": {"out": 0, "inn": 12},
}
REST = {"s": 1.0, "x": 0.0, "y": 0.0, "r": 0.0, "bx": 0.0, "by": 0.0}


def _ein(p):
    return p * p


def _eout(p):
    return 1 - (1 - p) ** 3


def _peak(p, k):
    p = p or {}
    return {"s": 1 + (p.get("s", 1) - 1) * k, "x": p.get("x", 0) * k, "y": p.get("y", 0) * k, "r": p.get("r", 0) * k,
            "bx": p.get("bx", 0) * k, "by": p.get("by", 0) * k}


def _mix(a, b, p):
    return {n: a[n] + (b[n] - a[n]) * p for n in REST}


def cover(x, y, r, ox, oy, w=W, h=H):
    """Smallest scale at which a frame moved by (x, y, r deg) about (ox, oy) still covers a w x h canvas.
    Adapted from reel-kit camera-transitions cover() (MIT)."""
    if abs(x) < 0.01 and abs(y) < 0.01 and abs(r) < 0.001:
        return 1.0
    a = math.radians(r)
    c, n = math.cos(a), math.sin(a)
    need = 1.0
    for px, py in ((-0.5, -0.5), (w + 0.5, -0.5), (-0.5, h + 0.5), (w + 0.5, h + 0.5)):
        dx, dy = px - ox - x, py - oy - y
        u, v = c * dx + n * dy, -n * dx + c * dy
        need = max(need, u / (w - ox) if u > 0 else -u / ox, v / (h - oy) if v > 0 else -v / oy)
    return need


def transition_keys(move, cut_f, strength, point=None, last_f=-1):
    """-> {'T': rows for #mvT [f,s,x,y,r,bx,by], 'iris': rows [f,o,r,cx,cy], 'flash': rows [f,o], 'rack': rows [f,blur]},
    frames (first, last)."""
    m = MOVES[move]
    out = {"T": [], "iris": [], "flash": [], "rack": []}
    ox, oy = T_ORIGIN
    k = strength

    def key(f, kk):
        x, y, r = round(kk["x"], 1), round(kk["y"], 1), round(kk["r"], 3)   # cover the values actually written
        s = max(kk["s"], cover(x, y, r, ox, oy))
        out["T"].append([f, math.ceil(s * 10000 - 1e-9) / 10000, x, y, r, round(kk["bx"], 1), round(kk["by"], 1)])

    if move in ("whip", "zoom", "push", "drop", "smash"):
        po, pi = _peak(m.get("peakOut"), k), _peak(m.get("peakIn"), k)
        for i in range(m["out"]):
            f = cut_f - m["out"] + i
            if f > last_f:
                key(f, _mix(REST, po, _ein((i + 1) / m["out"])))
        for j in range(m["inn"]):
            key(cut_f + j, _mix(pi, REST, _eout(j / m["inn"])))
        key(cut_f + m["inn"], REST)
        if move == "smash":
            out["flash"] = [[cut_f, 0.55 * k], [cut_f + 1, 0.3 * k], [cut_f + 2, 0.12 * k], [cut_f + 3, 0.0]]
    elif move == "iris":
        cx, cy = point or (540, 900)
        far = 2400
        for i in range(m["out"]):          # closes onto the point
            f = cut_f - m["out"] + i
            if f > last_f:
                p = _ein((i + 1) / m["out"])
                out["iris"].append([f, 1, round(far * (1 - p) + 2, 1), cx, cy])
        for j in range(m["inn"]):          # opens from it on the new shot
            p = _eout((j + 1) / (m["inn"] + 1))
            out["iris"].append([cut_f + j, 1, round(far * p, 1), cx, cy])
        out["iris"].append([cut_f + m["inn"], 0, far, cx, cy])
    elif move == "flash":
        out["flash"] = [[cut_f, round(0.8 * k, 3)]] + [[cut_f + j, round(0.8 * k * (1 - _eout(j / m["inn"])), 3)]
                                                      for j in range(1, m["inn"])] + [[cut_f + m["inn"], 0.0]]
    elif move == "rack":
        out["rack"] = [[cut_f + j, round(7 * k * (1 - _eout(j / m["inn"])), 2)] for j in range(m["inn"])] + [[cut_f + m["inn"], 0.0]]
    first = cut_f - m["out"] if m["out"] else cut_f
    return out, (first, cut_f + m["inn"])


# ---------------------------------------------------------------------------------------------- planner
def _smooth_noise(seed, t, freqs=(0.17, 0.31, 0.53)):
    import random
    rnd = random.Random(seed)
    ph = [rnd.random() * 6.283 for _ in freqs]
    return sum(math.sin(2 * math.pi * f * t + p) / (i + 1) for i, (f, p) in enumerate(zip(freqs, ph))) / 1.83


def _word_starts(words, t0, t1, pad0=0.0, pad1=0.0):
    out = []
    prev_end = None
    for w in words:
        s = float(w["start"])
        if t0 + pad0 <= s <= t1 - pad1:
            gap = s - prev_end if prev_end is not None else 1.0
            out.append((s, gap, w["text"]))
        prev_end = float(w["end"])
    return out


def plan(*, frames, cuts, shots, words, accents=(), graphic_events=(), cfg, cutout_windows=(), alive=None,
         strong_events=None, log=print):
    """cuts:   [{"t", "section": bool, "visible": bool (speaker on either side), "into": seg id, "override": {}}]
       shots:  [{"t0", "t1", "seg", "layout", "visible", "ox", "oy", "face_h", "kmax"?, "override": {}}]  (ox/oy in the
               camera layer's own pixels: the speaker video's 1080x1920 space)
       words:  words.json rows; accents: lowercase words that get a punch / caption stamp
       graphic_events: times (s) of graphic entrances already on screen (inserts, beat starts)
       strong_events: the subset big enough to move the picture on its own (new inserts, slides, flips); small
               ticks and pops do not stop a still stretch from counting as still
       alive: per output frame 0/1, the plate moves on its own (plate_activity + alive_from)
    -> plan dict (also the QA contract): camera rows, transition rows, events, report."""
    total = frames / FPS
    lvl = cfg["level"]
    events = []      # {"t", "kind", "what", "sound"?, "src": "motion"}
    trans = []

    # ---- transitions (budgeted)
    last_f, last_t, used = -1, -99.0, 0
    for c in cuts:
        ov = c.get("override") or {}
        ccfg = for_level(cfg, c.get("level") if c.get("level") in LEVELS else seg_level(ov, cfg))   # the beat cut into
        every = ccfg["transitions"] == "every-cut"
        gap = 10.0 / ccfg["per10s"] if ccfg.get("per10s") else 1e9
        want = ov.get("transition")
        if want and want != "none" and want not in MOVES:
            log(f"  WARN unknown transition '{want}' on the cut into {c.get('into')}; known: {', '.join(MOVES)}")
            want = None
        if want == "none" or ccfg["transitions"] == "off" and not want:
            continue
        if any(w0 - 0.05 <= c["t"] <= w1 + 0.05 for w0, w1 in cutout_windows):
            continue          # a cut-out window never spans a transition
        if not want:
            if not (every or c.get("section")):
                continue
            if c["t"] < 0.5 or c["t"] > total - 1.0 or c["t"] - last_t < (0.45 if every else gap):
                continue
        if not want and not ccfg["moves"]:
            continue
        move = want if want in MOVES else ccfg["moves"][used % len(ccfg["moves"])]
        if move == "iris" and not c.get("point"):
            move = "whip" if "whip" in ccfg["moves"] or not ccfg["moves"] else ccfg["moves"][0]
        cf = int(round(c["t"] * FPS))
        if cf - MOVES[move]["out"] <= last_f:
            continue
        keys, span = transition_keys(move, cf, ccfg["strength"] or 0.85, c.get("point"), last_f)
        trans.append({"t": round(c["t"], 3), "frame": cf, "move": move, "span": span, "keys": keys,
                      "name": VOCAB[move], "into": c.get("into"), **({"override": True} if want else {})})
        events.append({"t": round(c["t"], 3), "kind": "transition", "what": move, "sound": SOUND.get(move), "src": "motion"})
        last_f, last_t, used = span[1], c["t"], used + 1
    tcuts = {tr["frame"] for tr in trans}

    # ---- camera: per shot, per frame
    acc = {a.lower().strip(".,!?") for a in accents}
    punches, reframes = [], []
    cam_shots = []
    for sh in shots:
        f0, f1 = int(round(sh["t0"] * FPS)), int(round(sh["t1"] * FPS))
        ov = sh.get("override") or {}
        if not sh.get("visible") or f1 <= f0:
            continue
        lv = seg_level(ov, cfg)
        cam_shots.append({**sh, "f0": f0, "f1": f1, "level": lv, "cfg": for_level(cfg, lv)})
    still_shots = {id(s) for s in cam_shots if ov_camera(s.get("override")) == "still"}

    # punches on emphasis words (spaced, away from cuts)
    if any(x["cfg"]["punch"] > 1.0 for x in cam_shots):
        last = -99.0
        for w in words:
            n = _norm(w["text"]).strip("'")
            s = float(w["start"])
            if n not in acc:
                continue
            sh = next((x for x in cam_shots if x["t0"] + 0.45 <= s <= x["t1"] - 0.3), None)
            if not sh or id(sh) in still_shots or sh["cfg"]["punch"] <= 1.0 or s - last < sh["cfg"]["punch_gap"]:
                continue
            punches.append({"t": round(s - 0.02, 3), "shot": sh["seg"], "k": sh["cfg"]["punch"], "word": w["text"]})
            last = s
    for sh in cam_shots:   # explicit punches from overrides
        p = (sh.get("override") or {}).get("punch")
        if p:
            cur = WordCursor(words, sh["t0"], sh["t1"])
            t = cur.at(p, fallback=0.3, lead="push")
            punches.append({"t": round(t, 3), "shot": sh["seg"], "k": max(sh["cfg"]["punch"], 1.06), "word": p})

    def visual_times():
        ts = [0.0] + [c["t"] for c in cuts] + list(graphic_events) + [p["t"] for p in punches] + [r["t"] for r in reframes]
        ts += [tr["t"] for tr in trans]
        return sorted(ts + [total])

    def still_runs():
        """Stretches (s) where nothing would move: no event in the last 0.2 s and the plate itself is still
        (`alive`, from the A-roll's own motion scaled by how much of the frame the speaker fills)."""
        cov = [False] * frames
        strong = list(strong_events) if strong_events is not None else list(graphic_events)
        ts = [0.0] + [c["t"] for c in cuts] + strong + [p["t"] for p in punches] + [r["t"] for r in reframes] + \
            [tr["t"] for tr in trans]
        for t in ts:
            for f in range(max(0, int(t * FPS)), min(frames, int((t + 0.2) * FPS) + 1)):
                cov[f] = True
        if alive is not None:
            cov = [c or bool(alive[f]) if f < len(alive) else c for f, c in enumerate(cov)]
        runs, f0 = [], None
        for f, c in enumerate(cov + [True]):
            if not c and f0 is None:
                f0 = f
            elif c and f0 is not None:
                runs.append((f0 / FPS, f / FPS))
                f0 = None
        return runs

    # fillers (WIDE/CLOSE reframes alternating with punches) only where the picture would otherwise sit still
    fillers = []
    if any(x["cfg"].get("fill_gap") and x["cfg"]["reframe"] > 1.0 for x in cam_shots):
        for _ in range(160):
            added = False
            for a, b in still_runs():
                cands = []
                for sh in cam_shots:
                    sc = sh["cfg"]
                    fg = sc.get("fill_gap")
                    if not fg or sc["reframe"] <= 1.0 or id(sh) in still_shots or sh.get("layout") in ("stage", "media"):
                        continue
                    if min(b, sh["t1"]) - max(a, sh["t0"]) <= fg:      # judged by THIS beat's own level
                        continue
                    # walk the stretch left to right: switch just before it would count as dead
                    lo, hi = max(a + 0.45, sh["t0"] + 0.35), min(a + fg, b - 0.05, sh["t1"] - 0.2)
                    prev_f = max([x for x in fillers if x <= hi] or [-99])
                    lo = max(lo, prev_f + sc["filler_gap"])
                    if hi < lo:
                        continue
                    for s_, g, txt in _word_starts(words, lo, hi):
                        # latest phrase start in reach wins (a word after a pause gets a bonus)
                        cands.append(((hi - s_) - 0.6 * min(g, 0.3), s_, sh))
                    cands.append((0.25, hi, sh))      # nothing to land on: switch on time
                cands = [c for c in cands if all(abs(c[1] - x) >= c[2]["cfg"]["filler_gap"] for x in fillers)]
                if os.environ.get("RRM_DEBUG"):
                    log(f"    still {a:.2f}-{b:.2f}: {len(cands)} candidates")
                if not cands:
                    continue
                cands.sort(key=lambda x: x[0])
                _, s_, sh = cands[0]
                fillers.append(s_)
                sc = sh["cfg"]
                if len(fillers) % 2 == 0 and sc["punch"] > 1.0:     # every other filler is a punch: less repetitive
                    punches.append({"t": round(s_ - 0.02, 3), "shot": sh["seg"], "k": sc["punch"], "word": "(filler)"})
                else:
                    prev = [r for r in reframes if r["shot"] == sh["seg"] and r["t"] < s_]
                    close = not (prev and prev[-1]["close"])
                    k = sc["reframe"] if sh.get("layout") != "full" else min(sc["reframe"], 1.06)
                    reframes.append({"t": round(s_ - 0.02, 3), "shot": sh["seg"], "close": close, "k": k if close else 1.0})
                added = True
                break
            if not added:
                break
    for sh in cam_shots:
        cam = ov_camera(sh.get("override"))
        if cam == "still" and (sh.get("override") or {}).get("frame") in ("close", "wide"):
            cam = sh["override"]["frame"]   # a still shot that opens on a held framing switch (a thought break)
        if cam in ("close", "wide"):
            k = sh["cfg"]["reframe"] if sh["cfg"]["reframe"] > 1 else 1.08
            reframes.append({"t": sh["t0"], "shot": sh["seg"], "close": cam == "close", "k": k if cam == "close" else 1.0})

    # per-frame camera values
    cam_rows, origin_rows = [], []
    prev_row = None
    settle_cuts = []
    for sh in cam_shots:
        sc = sh["cfg"]
        f0, f1 = sh["f0"], sh["f1"]
        dur = max(1e-3, sh["t1"] - sh["t0"])
        push_amt = 0.0 if id(sh) in still_shots else min(sc["push"] * (2.0 if ov_camera(sh.get("override")) == "push" else 1.0),
                                                            0.012 * dur + 0.006)
        settle = sc["settle"] if f0 not in tcuts and f0 > 0 or (f0 == 0 and sh["level"] != "simple") else 1.0
        if id(sh) in still_shots:
            settle = 1.0
        if settle > 1.0:
            settle_cuts.append(round(sh["t0"], 3))
            events.append({"t": round(sh["t0"], 3), "kind": "settle", "what": sh["seg"], "src": "motion"})
        sp = [p for p in punches if p["shot"] == sh["seg"] and sh["t0"] <= p["t"] < sh["t1"]]
        rf = sorted([r for r in reframes if r["shot"] == sh["seg"] and sh["t0"] - 1e-3 <= r["t"] < sh["t1"]], key=lambda r: r["t"])
        origin_rows.append([f0, round(sh["ox"], 1), round(sh["oy"], 1)])
        seed = zlib.crc32(str(sh["seg"]).encode()) % 9973
        for f in range(f0, f1):
            t = f / FPS
            p = (t - sh["t0"]) / dur
            s = 1.0 + push_amt * p
            ps = (t - sh["t0"]) / 0.32
            if settle > 1.0 and ps < 1:
                s *= 1 + (settle - 1) * (1 - (1 - (1 - ps) ** 2))   # power2.out from settle to 1
            base = 1.0
            for r in rf:
                if t >= r["t"] - 1e-6:
                    base = r["k"]
                    pr = (t - r["t"]) / 0.12
                    if pr < 1 and r["close"]:
                        base *= 1 + 0.022 * (1 - pr) ** 2
            s *= base
            for pu in sp:
                pp = (t - pu["t"]) / 0.2
                if 0 <= pp < 1:
                    s *= 1 + (pu["k"] - 1) * (1 - pp) ** 3     # hit, then power3.out back
            x = y = r = 0.0
            if sc["handheld"] and id(sh) not in still_shots:
                x = 4.0 * _smooth_noise(seed, t)
                y = 3.0 * _smooth_noise(seed + 1, t, (0.13, 0.29, 0.47))
                r = 0.12 * _smooth_noise(seed + 2, t, (0.11, 0.23))
            s = min(s, sh.get("kmax", 9.0))         # a layout can cap the camera (face near captions or cards)
            x, y, r = round(x, 1), round(y, 1), round(r, 3)
            s = max(s, cover(x, y, r, sh["ox"], sh["oy"]))
            row = [f, math.ceil(s * 10000 - 1e-9) / 10000, x, y, r]
            if prev_row is None or row[1:] != prev_row[1:]:
                cam_rows.append(row)
            prev_row = row
    for p in punches:
        events.append({"t": p["t"], "kind": "punch", "what": p["word"], "src": "motion"})
    for r in reframes:
        events.append({"t": r["t"], "kind": "reframe", "what": "close" if r["close"] else "wide", "src": "motion"})
    events.sort(key=lambda e: e["t"])
    report = {"level": lvl, "transitions": len(trans), "punches": len(punches), "reframes": len(reframes), "fillers": len(fillers),
              "settles": len(settle_cuts), "moves": [tr["move"] for tr in trans]}
    log(f"  motion {lvl}: {len(trans)} transitions ({', '.join(report['moves']) or 'none'}), {len(settle_cuts)} settles, "
        f"{len(punches)} punches, {len(reframes)} reframes")
    return {"version": 1, "level": lvl, "frames": frames, "config": {k: cfg.get(k) for k in ("sfx", "grain", "vignette", "handheld",
            "transitions", "per10s", "moves", "captions", "targets", "parallax")}, "transitions": trans, "camera": cam_rows,
            "origins": origin_rows, "punches": punches, "reframes": reframes, "settles": settle_cuts, "events": events,
            "levels": level_spans(shots, cfg, total), "report": report}


def plate_activity(video, frames, cache=None):
    """Per output frame (30 fps): mean abs gray diff of the plate itself (90x160, 15 fps, the QA metric's scale).
    Cached in `cache` (json) by file size + mtime."""
    st = os.stat(video)
    sig = f"{st.st_size}:{int(st.st_mtime)}:{frames}"
    if cache and os.path.exists(cache):
        try:
            d = json.load(open(cache))
            if d.get("sig") == sig:
                return d["diff"]
        except ValueError:
            pass
    import subprocess
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", "fps=15,scale=90:160,format=gray", "-f", "rawvideo",
                        "-"], capture_output=True, timeout=900)
    raw = p.stdout[: len(p.stdout) // (160 * 90) * (160 * 90)]
    if p.returncode or not raw:
        return None      # no liveness map: the planner treats the plate as still (more fillers, never fewer)
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 160, 90).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)) if len(fr) > 1 else np.zeros(1)
    out = [round(float(d[min(len(d) - 1, max(0, f // 2 - 1))]), 2) for f in range(frames)]
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump({"sig": sig, "diff": out}, open(cache, "w"))
    return out


def alive_from(diff, shots, frames, still=2.5, share=None):
    """Which output frames move on their own: plate diff x the share of the frame the speaker fills >= still.
    diff None (no measurement) -> None.
    Conservative on purpose (a split or card layout shows only part of the plate, often the stillest part)."""
    if diff is None:
        return None
    share = share or {"full": 0.8, "split": 0.35, "card": 0.35, "overlay": 0.8}
    out = [0] * frames
    for sh in shots:
        k = share.get(sh.get("layout"), 1.0) if sh.get("visible") else 0.0
        for f in range(int(round(sh["t0"] * FPS)), min(frames, int(round(sh["t1"] * FPS)))):
            if f < len(diff) and diff[f] * k >= still:
                out[f] = 1
    return out


def camera_at(plan_, frame):
    """(scale, x, y, rotation, ox, oy) of the speaker camera on a frame (QA maps face boxes through it)."""
    s = (1.0, 0.0, 0.0, 0.0)
    for r in plan_.get("camera", []):
        if r[0] > frame:
            break
        s = tuple(r[1:5])
    o = (540.0, 960.0)
    for r in plan_.get("origins", []):
        if r[0] > frame:
            break
        o = (r[1], r[2])
    return s + o


def transition_frames(plan_):
    out = set()
    for tr in plan_.get("transitions", []):
        out |= set(range(tr["span"][0], tr["span"][1] + 1))
    return out


# ---------------------------------------------------------------------------------------------- emit
def emit_js(plan_, cam_sel="#mvCam", t_sel="#mvT", words=None):
    js = []
    if words is not None:
        js.append("RRM.setWords(" + json.dumps([[round(float(w["start"]), 3), round(float(w["end"]), 3), w["text"]]
                                                for w in words]) + ");")
    if plan_["origins"]:
        for f, ox, oy in plan_["origins"]:
            js.append(f"tl.set({json.dumps(cam_sel)},{{transformOrigin:'{ox}px {oy}px'}},{max(0.0, (f - 0.5) / FPS):.5f});")
    if plan_["camera"]:
        js.append(f"RRM.keys(tl,{json.dumps(cam_sel)},['scale','x','y','rotation']," + json.dumps(plan_["camera"],
                  separators=(",", ":")) + ");")
    for px in (plan_.get("config") or {}).get("parallax") or []:   # depth: a layer follows the camera by factor k
        k = float(px.get("k", 0.3))
        rows = [[r[0], round(1 + (r[1] - 1) * k, 4), round(r[2] * k, 1), round(r[3] * k, 1), round(r[4] * k, 3)]
                for r in plan_["camera"]]
        if rows:
            js.append(f"RRM.keys(tl,{json.dumps(px['sel'])},['scale','x','y','rotation']," + json.dumps(rows, separators=(",", ":")) + ");")
    for tr in plan_["transitions"]:
        k = tr["keys"]
        if k["T"]:
            js.append(f"RRM.keys(tl,{json.dumps(t_sel)},['scale','x','y','rotation','bx','by']," + json.dumps(k["T"], separators=(",", ":")) + ");")
        if k["iris"]:
            js.append("RRM.keys(tl,'#mvIris',['o','r','cx','cy']," + json.dumps(k["iris"], separators=(",", ":")) + ");")
        if k["flash"]:
            js.append("RRM.keys(tl,'#mvFlash',['o']," + json.dumps(k["flash"], separators=(",", ":")) + ");")
        if k["rack"]:
            js.append(f"RRM.keys(tl,{json.dumps(cam_sel)},['blur']," + json.dumps(k["rack"], separators=(",", ":")) + ");")
    return js


def css(cfg, iris_color="#0C0C0F", z="1"):
    vig = cfg.get("vignette") or 0
    return f"""
/* motion v2 (engine/motion) */
#mvT{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:{z};transform-origin:{T_ORIGIN[0]}px {T_ORIGIN[1]}px}}
#mvCam{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:540px 960px}}
.mv-vid{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.mv-vid video{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}}
.mv-behind{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;white-space:nowrap;opacity:0;visibility:hidden}}
.mv-behind .w{{display:inline-block;line-height:1;letter-spacing:-.04em}}
#mvVig{{position:absolute;left:0;top:0;width:1080px;height:1920px;pointer-events:none;z-index:2;
  background:radial-gradient(125% 88% at 50% 44%,rgba(0,0,0,0) 56%,rgba(12,8,6,{vig:.3f}) 100%);{'' if vig else 'display:none;'}}}
#mvIris{{position:absolute;left:540px;top:900px;width:0;height:0;border-radius:50%;z-index:40;pointer-events:none;
  opacity:0;visibility:hidden;box-shadow:0 0 0 4200px {iris_color}}}
#mvFlash{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:41;background:#fff;opacity:0;visibility:hidden;pointer-events:none}}
#mvGrain{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:42;pointer-events:none;background-size:320px 320px;
  mix-blend-mode:overlay;opacity:.08}}
.rm-mask{{display:inline-block;overflow:hidden;vertical-align:top;padding:0 .04em .1em;margin:0 -.04em -.1em}}
.rm-in{{display:inline-block}}
.rc,.rw{{display:inline-block;will-change:transform}}
.mv-depth{{box-shadow:0 18px 30px rgba(12,12,15,.16),0 3px 8px rgba(12,12,15,.10),inset 0 0 0 1.5px rgba(12,12,15,.06)}}
.mv-glow{{text-shadow:0 0 22px currentColor,0 0 4px currentColor}}
"""


DEFS_HTML = ('<svg id="mvDefs" width="0" height="0" style="position:absolute" aria-hidden="true">'
             '<filter id="mvMB" x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">'
             '<feGaussianBlur id="mvMBg" in="SourceGraphic" stdDeviation="0 0" result="b"/>'
             '<feComponentTransfer in="b"><feFuncA type="table" tableValues="1 1"/></feComponentTransfer></filter></svg>')


def top_layers_html(cfg, grain_src=None):
    """Iris + flash (+ grain) layers. They live INSIDE #mvT's parent stack but above the picture; captions stay above
    the flash in the split engine (z 20 < 40) only when placed after; templates decide where to insert this."""
    g = f'<div id="mvGrain" style="background-image:url({grain_src})"></div>' if (cfg.get("grain") and grain_src) else ""
    return f'<div id="mvIris"></div><div id="mvFlash"></div>{g}'


def grain_js(cfg, frames):
    return [f"RRM.grain(tl,'#mvGrain',0,{frames / FPS:.3f},21,2);"] if cfg.get("grain") else []


def ensure_assets(project, cfg=None):
    """Copy motion.js into the project (assets/rrm-motion.js); write the grain tile when grain is on.
    Returns (script_rel, grain_rel or None)."""
    dst = os.path.join(project, "assets", ASSET_NAME)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(JS_FILE, dst)
    grain = None
    if cfg and cfg.get("grain"):
        grain = "assets/rrm-grain.png"
        gp = os.path.join(project, grain)
        if not os.path.exists(gp):
            make_grain(gp)
    return "assets/" + ASSET_NAME, grain


def make_grain(path, size=320, seed=1729):
    """Seeded gaussian noise tile, grey 128 = neutral under mix-blend-mode overlay."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, (size, size))
    n = (n + np.roll(n, 1, 0) + np.roll(n, 1, 1)) / 3
    img = np.clip(128 + n * 38, 0, 255).astype("uint8")
    Image.fromarray(img, "L").convert("RGB").save(path)


def caption_kind(text, accent_set, cfg, index=0):
    """Kinetic caption entrance for one caption chunk: None (plain), 'rise', 'stamp' (payoff word), 'grow'."""
    if cfg.get("captions") != "kinetic":
        return None
    words = [_norm(w) for w in str(text).split()]
    if any(w in accent_set for w in words):
        return "grow" if cfg["level"] == "showreel" and len(words) == 1 and index % 3 == 0 else "stamp"
    return "rise"


def write_plan(project, plan_, extra=None):
    out = dict(plan_)
    if extra:
        out.update(extra)
    os.makedirs(os.path.join(project, "work"), exist_ok=True)
    with open(os.path.join(project, "work", "motion_plan.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return os.path.join(project, "work", "motion_plan.json")


def load_plan(project):
    p = os.path.join(project, "work", "motion_plan.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)
