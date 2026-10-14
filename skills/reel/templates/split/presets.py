"""presets.py: named looks the split engine applies before it composes (project.json "preset": "<id>").

A preset fills in project settings (motion, captions), the camera per segment and the top-slot plan. Anything the
project sets explicitly wins: project keys over preset defaults (dicts merged key by key), an edl segment's own
`motion`, `top` and `mode` over the preset's. apply() returns new dicts; nothing on disk changes.

kallaway (split-deck, after the research in our own research notes, our own look and wording):
  - split held for most of the reel (top slot = 50 %, speaker plate below, camera still inside a thought)
  - the top slot changes picture about every 1.0 s (0.8 to 1.4) from the B-roll feeder (feed.py), kit cards after
  - topic banner (label-pill tag, 3 to 5 words) readable on frame 1 for about 2.5 s       project "banner"
  - receipt-proof beat on segments marked "purpose": "proof" (+ "proof": {...} args)     kallaway.proof_screen
  - one full-frame talking-head analogy beat: segment "purpose": "analogy" or "layout": "full" (the calm beat:
    level simple, a held close framing on the cut into it, no graphics, nothing else moves)
  - head bubble over a full-screen graphic: segment "bubble": {...} (one shot only)        kallaway.head_bubble
  - keyword comment CTA at the end: project "cta": {"keyword": ..., "at": ..., "dm_at": "#seg"}
  the house rules on top: calm captions (fade/rise chunks, at most one accent word), light SFX 18-22 dB under the voice
  (a soft swish on at most every other top-slot change), zoom changes on the face only at thought breaks, no grain.
"""
import json
import os
import re

import feed
import timeline as tl_

KALLAWAY = {
    "project": {
        "motion": {"level": "polished", "sfx": "light", "grain": False, "transitions": "off"},
        "captions": {"mode": "pill", "max_words": 4, "calm": True, "accent_max": 1, "full_style": "pill"},
    },
    "feed": {"every": 1.0, "min": 0.8, "max": 1.4, "dir": "assets/broll", "push": 0.06, "drift": 26, "swish_every": 2},
    "banner": {"dur": 2.5},
    "analogy_camera": {"level": "simple", "camera": "still", "frame": "close"},
}
PRESETS = {"kallaway": KALLAWAY}
BREAK = re.compile(r"[.?!]['\"]?$")


def merge(base, over):
    """Deep merge: `over` wins; dicts merge key by key; returns a new dict."""
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _segments(project):
    path = os.path.join(project, "segments.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise SystemExit(f"preset: cannot read {path}: {e}")


def seg_times(project):
    try:
        return {s["id"]: (s["frame"] / tl_.FPS, (s["frame"] + s["frames"]) / tl_.FPS) for s in _segments(project)}
    except KeyError as e:
        raise SystemExit(f"preset: segments.json row without {e}")


def _explicit(project, edl, beats, words):
    """Windows of the project's own beats (any anchor form compose accepts), so the feed never lands on them."""
    segs = tl_.load_segments(edl, _segments(project))
    w = tl_.Words(words)
    out = []
    for pb in beats or []:
        t0 = tl_.resolve_beat_time(pb, segs, w)
        s = tl_.seg_at(segs, t0)
        if "until" in pb:
            t1 = float(pb["until"])
        elif "until_word" in pb:
            t1 = w.find(pb["until_word"], t0 + 0.05) or s["t1"]
        elif "dur" in pb:
            t1 = t0 + float(pb["dur"])
        else:
            t1 = s["t1"]
        out.append((t0, min(t1, s["t1"])))
    return out


def _with_lines(project, edl):
    """edl rows with `line` filled from segments.json when the edl has none (thought-break detection reads it)."""
    lines = {s["id"]: s.get("line", "") for s in _segments(project)}
    return [e if e.get("line") else {**e, "line": lines.get(e["id"], "")} for e in edl]


def _is_analogy(e):
    return e.get("purpose") == "analogy" or e.get("layout") == "full"


def _camera(edl, warn):
    """Per segment camera: still inside a thought; on a thought break (sentence end, layout change) alternate a
    close / wide framing ON the cut; the analogy beat is the calm one (level simple, held close framing). A segment's
    own `motion` wins."""
    out, close, prev = [], False, None
    for e in edl:
        e = dict(e)
        brk = prev is not None and (BREAK.search(prev.get("line", "").strip()) or _is_analogy(prev) != _is_analogy(e))
        if _is_analogy(e):
            want = dict(KALLAWAY["analogy_camera"])
        elif brk:
            close = not close
            want = {"camera": "still", "frame": "close" if close else "wide"}
        else:
            want = {"camera": "still"}
        e["motion"] = {**want, **(e.get("motion") or {})}
        out.append(e)
        prev = e
    if sum(1 for e in edl if _is_analogy(e)) > 1:
        warn("preset kallaway: more than one analogy (full-frame) beat; the look wants one per reel")
    return out


def _layout(edl):
    """Split everywhere except the analogy beat (a segment with "keep_mode": true keeps its own mode and top); a proof
    segment without its own top gets the proof screen; an empty or "feed" top joins the feed."""
    out = []
    for e in edl:
        e = dict(e)
        if e.get("keep_mode"):
            pass
        elif _is_analogy(e):
            e["mode"], e["top"] = "full", None
        else:
            e["mode"] = "split"
            if e.get("top") == "feed":
                e["top"] = None
            if e.get("purpose") == "proof" and e.get("proof") and not e.get("top"):
                e["top"] = {"insert": "proof_screen", "args": e["proof"]}
        out.append(e)
    return out


def _overlays(pj, edl, times, words, cfg):
    """Banner on frame 1, a head bubble per segment that asks for one, the CTA at the end. -> (overlays, covered)."""
    ovs, covered = [], []
    ban = pj.get("banner")
    if ban:
        ban = {"text": ban} if isinstance(ban, str) else dict(ban)
        dur = float(ban.get("dur", cfg["banner"]["dur"]))
        ovs.append({"insert": "topic_banner", "args": {**ban, "dur": dur}, "from": 0, "until": round(dur + 0.25, 3)})
    for e in edl:
        bub = e.get("bubble")
        if not bub:
            continue
        t0, t1 = times[e["id"]]
        a0 = max(t0, float(bub.get("from", t0)))
        ovs.append({"insert": "head_bubble", "args": dict(bub), "from": round(a0, 3), "until": round(t1, 3)})
        covered.append((a0, t1))
    cta = pj.get("cta")
    if cta:
        total = max(t for _, t in times.values())
        t0 = _word_time(words, cta.get("from"), total - 4.0)
        ovs.append({"insert": "comment_cta", "args": {k: v for k, v in cta.items() if k != "from"}, "from": round(t0, 3),
                    "until": round(total, 3)})
        covered.append((t0, total))
    return ovs, covered


def _word_time(words, spec, default):
    if isinstance(spec, (int, float)):
        return float(spec)
    if isinstance(spec, str) and spec.startswith("@"):
        m = re.match(r"^@(.+?)(?::(\d+))?$", spec)
        if not m:
            return max(0.0, default)
        hits = [w for w in words if feed._norm(w["text"]) == feed._norm(m.group(1))]
        n = int(m.group(2) or 1)
        if len(hits) >= n:
            return float(hits[n - 1]["start"]) - 0.04
    return max(0.0, default)


def _free(edl, times, covered, explicit):
    """Feed ranges: split segments with no insert of their own, minus covered windows and explicit project beats."""
    out = []
    for e in edl:
        if e.get("mode", "split") != "split" or e.get("top"):
            continue
        rs = [times[e["id"]]]
        for a, b in list(covered) + list(explicit):
            nxt = []
            for lo, hi in rs:
                if b <= lo or a >= hi:
                    nxt.append((lo, hi))
                    continue
                nxt += [x for x in ((lo, a), (b, hi)) if x[1] - x[0] > 0.05]
            rs = nxt
        out += rs
    return out


def apply(project, pj, edl, words, warn=print):
    """-> (pj, edl) with the preset applied, plus pj["_preset"] = report. Unknown or no preset: unchanged."""
    name = pj.get("preset")
    if not name:
        return pj, edl
    if name not in PRESETS:
        warn(f"unknown preset '{name}' (known: {', '.join(PRESETS)}); composing without it")
        return pj, edl
    cfg = PRESETS[name]
    out = merge(cfg["project"], pj)
    times = seg_times(project)
    edl2 = _camera(_layout(_with_lines(project, edl)), warn)
    ovs, covered = _overlays(out, edl2, times, words, cfg)
    explicit = _explicit(project, edl2, out.get("beats"), words)
    fcfg = merge(cfg["feed"], out.get("feed") or {})
    beats, rep = feed.plan(_free(edl2, times, covered, explicit), words, feed.sources(project, fcfg["dir"]), times, fcfg)
    out["beats"] = list(out.get("beats", [])) + beats
    out["overlays"] = list(out.get("overlays", [])) + ovs
    if not out["captions"].get("accent"):
        out["captions"]["accent"] = sorted({feed._norm(w["text"]) for w in words if re.search(r"\d", w["text"])})
    out["_preset"] = {"name": name, "feed": rep, "covered": [[round(a, 3), round(b, 3)] for a, b in covered]}
    return out, edl2


def caption_slices(slices):
    """Caption chunks never span a slice; with the feed the top slot changes every second, which is not a reason to
    break a caption. Merge neighbouring slices with the same segment and layout (the speaker does not change)."""
    out = []
    for s in slices:
        if out and out[-1]["seg"] == s["seg"] and out[-1]["layout"] == s["layout"] and abs(out[-1]["t1"] - s["t0"]) < 1e-4:
            out[-1] = {**out[-1], "t1": s["t1"]}
        else:
            out.append(dict(s))
    return out
