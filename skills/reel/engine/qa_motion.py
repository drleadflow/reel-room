#!/usr/bin/env python3
"""qa_motion.py: Motion v2 QA gates. Called by engine/qa.py, templates/split/styleqa.py and templates/stylekit/skqa.py;
also runs alone:

  python qa_motion.py <project> <render.mp4> [--out <qa dir>] [--level simple|polished|showreel] [--json]

Gates (names in qa/report.json; `label` is the plain-language name), targets per motion level:
  motion_density     "Keeps moving": mean frame-to-frame motion and % of frames moving (90x160 gray diff, 15 fps)
                     polished >= 4.5 mean and >= 55 % moving, showreel >= 6 and >= 70 %; simple exempt
  dead_frames        "No dead stretches": longest still (diff < 2) <= 1.2 s polished, 0.8 s showreel; simple exempt;
                     project.json motion.still_max overrides
  event_density      "Something new often enough": visual events (graphics, camera moves, transitions, stamps) per
                     second of speech >= 1.2 polished, 2.0 showreel; lists every 1.5 s stretch with no event
  hdr_alpha          "Cut-outs stay cut out": no composition video is HDR-tagged (HLG/PQ/bt2020); every alpha video
                     still has alpha; inside each cut-out window the render differs from the plate
  ease_lint          "Entrances snap in": no entrance (from opacity 0) on a linear or ease-in curve; counts raw ease names
                     outside the motion tokens (info) and opacity-only entrances on hero elements (data-hero)
  hero_scale         "Hero graphic is big enough": the biggest graphic of each graphic beat is >= 60 % of the frame width
                     (polished/showreel); simple exempt
  sfx_sync           "Sounds land on the picture": every placed SFX peaks within +-2 frames of its event, and the SFX bus
                     stays >= 18 dB under the voice
  behind_head        "Words behind the head stay readable": the head hides at most 2 letters of a behind-head word
  transition_budget  "Transitions are not overdone": count <= the level budget, none inside a cut-out window
  motion_strips      12 fps contact strips around every transition and the busiest graphic beats (qa/motion_strip_*.jpg)
Writes <qa>/motion.json (metrics, per-second motion sparkline, still stretches, event list).
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "motion"))
import motion as M  # noqa: E402

FPS = 30
MW, MH, MFPS = 90, 160, 15
DEAD = 2.0
NAMES = ["motion_density", "dead_frames", "event_density", "hdr_alpha", "ease_lint", "hero_scale", "sfx_sync",
         "behind_head", "transition_budget", "motion_strips"]
LABELS = {
    "motion_density": "Keeps moving", "dead_frames": "No dead stretches", "event_density": "Something new often enough",
    "hdr_alpha": "Cut-outs stay cut out", "ease_lint": "Entrances snap in", "hero_scale": "Hero graphic is big enough",
    "sfx_sync": "Sounds land on the picture", "behind_head": "Words behind the head stay readable",
    "transition_budget": "Transitions are not overdone", "motion_strips": "12 fps review strips",
}


def _check(name, ok, detail, skipped=False, **extra):
    d = {"name": name, "label": LABELS.get(name, name), "pass": bool(ok), "detail": detail}
    if skipped:
        d["skipped"] = True
    d.update(extra)
    return d


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------------------------- metrics
def metrics(render):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", render, "-vf", f"fps={MFPS},scale={MW}:{MH},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, MH, MW).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    t = np.arange(1, len(fr)) / MFPS
    stills, run0, best = [], None, 0.0
    for i, v in enumerate(d):
        if v < DEAD:
            run0 = t[i] - 1 / MFPS if run0 is None else run0
        else:
            if run0 is not None:
                stills.append((round(float(run0), 2), round(float(t[i - 1]), 2)))
            run0 = None
    if run0 is not None:
        stills.append((round(float(run0), 2), round(float(t[-1]), 2)))
    best = max([b - a for a, b in stills] or [0.0])
    persec = [round(float(d[(t >= s) & (t < s + 1)].mean()), 1) for s in range(int(t[-1]))] if len(t) else []
    return {"d": [round(float(x), 2) for x in d], "dur": round(len(fr) / MFPS, 2), "mean_motion": round(float(d.mean()), 2),
            "pct_frames_active": round(float((d > DEAD).mean() * 100), 1), "longest_still_s": round(best, 2),
            "stills": [s for s in stills if s[1] - s[0] >= 0.6], "persec": persec}


def spark(vals):
    bars = " .:-=+*#%@"
    return "".join(bars[min(len(bars) - 1, int(v / 2))] for v in vals)


# ---------------------------------------------------------------------------------------------- gates
def check_motion_density(m, tg):
    if not tg.get("motion_min"):
        return _check("motion_density", True, f"mean {m['mean_motion']}, {m['pct_frames_active']}% moving (simple: exempt)", True)
    ok = m["mean_motion"] >= tg["motion_min"] and m["pct_frames_active"] >= tg["active_min"]
    return _check("motion_density", ok, f"mean motion {m['mean_motion']} (target >= {tg['motion_min']}), "
                  f"{m['pct_frames_active']}% of frames moving (target >= {tg['active_min']}%)  {spark(m['persec'])}")


def check_dead_frames(m, tg):
    lim = tg.get("still_max")
    if not lim:
        return _check("dead_frames", True, f"longest still {m['longest_still_s']}s (simple: exempt)", True)
    over = [f"{a:.1f}-{b:.1f}s" for a, b in m["stills"] if b - a > lim]
    return _check("dead_frames", m["longest_still_s"] <= lim,
                  f"longest still {m['longest_still_s']}s (limit {lim}s)" + (f"; still stretches: {', '.join(over[:8])}" if over else ""))


# ---- per-beat levels: a reel can mix levels (a Simple beat inside a Showreel reel); each span meets its own targets
def level_groups(spans, cfg, pj):
    """{level: {"spans": [(a, b)], "tg": targets}} from plan["levels"]."""
    out = {}
    for a, b, lvl in spans:
        tg = dict(M.for_level(cfg, lvl)["targets"])
        if lvl != "simple" and (pj.get("motion") or {}).get("still_max") is not None:
            tg["still_max"] = float(pj["motion"]["still_max"])
        out.setdefault(lvl, {"spans": [], "tg": tg})["spans"].append((a, b))
    return out


def _inside(t, spans):
    return any(a - 1e-6 <= t < b for a, b in spans)


def check_motion_density_levels(m, groups):
    import numpy as np
    d = np.array(m["d"])
    t = np.arange(1, len(d) + 1) / MFPS
    parts, ok = [], True
    for lvl, g in sorted(groups.items()):
        mask = np.array([_inside(x, g["spans"]) for x in t])
        if not mask.any():
            continue
        mean, act = float(d[mask].mean()), float((d[mask] > DEAD).mean() * 100)
        tg = g["tg"]
        if not tg.get("motion_min"):
            parts.append(f"{lvl}: mean {mean:.2f}, {act:.0f}% moving (exempt)")
            continue
        good = mean >= tg["motion_min"] and act >= tg["active_min"]
        ok &= good
        parts.append(f"{lvl}: mean {mean:.2f} (>= {tg['motion_min']}), {act:.0f}% moving (>= {tg['active_min']}%)"
                     + ("" if good else " FAIL"))
    return _check("motion_density", ok, "per beat level: " + "; ".join(parts) + f"  {spark(m['persec'])}")


def check_dead_frames_levels(m, groups):
    bad, longest = [], {}
    spans = sorted((a, b, lvl) for lvl, g in groups.items() for a, b in g["spans"])
    for a, b in m["stills"]:
        for s0, s1, lvl in spans:
            lo, hi = max(a, s0), min(b, s1)
            if hi - lo <= 0:
                continue
            longest[lvl] = max(longest.get(lvl, 0.0), hi - lo)
            lim = groups[lvl]["tg"].get("still_max")
            if lim and hi - lo > lim:
                bad.append(f"{lo:.1f}-{hi:.1f}s ({lvl}, limit {lim}s)")
    det = ", ".join(f"{lvl} {longest.get(lvl, 0.0):.2f}s (limit {groups[lvl]['tg'].get('still_max') or 'exempt'})"
                    for lvl in sorted(groups))
    return _check("dead_frames", not bad, f"longest still per beat level: {det}" + (f"; over: {', '.join(bad[:6])}" if bad else ""))


def check_event_density_levels(plan, words, groups, extra=()):
    ev = visual_events(plan, extra)
    parts, ok = [], True
    for lvl, g in sorted(groups.items()):
        n = sum(1 for t in ev if _inside(t, g["spans"]))
        sp = max(0.5, sum(min(float(w["end"]), b) - max(float(w["start"]), a) for w in words for a, b in g["spans"]
                          if min(float(w["end"]), b) > max(float(w["start"]), a)))
        rate = n / sp
        need = g["tg"].get("events_per_s")
        good = not need or rate >= need
        ok &= good
        parts.append(f"{lvl}: {n} events / {sp:.1f}s speech = {rate:.2f}/s" + (f" (>= {need})" if need else " (exempt)")
                     + ("" if good else " FAIL"))
    return _check("event_density", ok, "per beat level: " + "; ".join(parts))


def speech_seconds(words):
    tot, cur = 0.0, None
    for w in sorted(words, key=lambda w: float(w["start"])):
        s, e = float(w["start"]), float(w["end"])
        if cur and s <= cur[1] + 0.35:
            cur[1] = max(cur[1], e)
        else:
            if cur:
                tot += cur[1] - cur[0]
            cur = [s, e]
    if cur:
        tot += cur[1] - cur[0]
    return tot


def visual_events(plan, extra=()):
    ev = [e["t"] for e in (plan or {}).get("events", [])]
    ev += [e["t"] for e in (plan or {}).get("graphic_events", [])]
    ev += list(extra)
    return sorted(set(round(float(t), 2) for t in ev))


def check_event_density(plan, words, tg, total, extra=()):
    ev = visual_events(plan, extra)
    sp = max(1.0, speech_seconds(words)) if words else max(1.0, total)
    rate = len(ev) / sp
    pts = [0.0] + ev + [total]
    holes = [f"{a:.1f}-{b:.1f}s" for a, b in zip(pts, pts[1:]) if b - a > 1.5]
    if not tg.get("events_per_s"):
        return _check("event_density", True, f"{len(ev)} visual events, {rate:.2f}/s of speech (simple: exempt)", True)
    return _check("event_density", rate >= tg["events_per_s"],
                  f"{len(ev)} visual events over {sp:.1f}s of speech = {rate:.2f}/s (target >= {tg['events_per_s']}); "
                  f"{len(holes)} stretch(es) over 1.5 s with no event" + (f": {', '.join(holes[:6])}" if holes else ""),
                  holes=holes)


def _frame(path, t, w=270, h=480):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf",
                          f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float32) if len(raw) == w * h else None


def check_hdr_alpha(project, render, index="index.html"):
    import hdr
    vids = hdr.composition_videos(project, index)
    bad, alpha_lost, probes = [], [], []
    html = open(os.path.join(project, index), encoding="utf-8").read() if os.path.exists(os.path.join(project, index)) else ""
    for v in vids:
        try:
            info = hdr.probe(v)
        except RuntimeError:
            continue
        rel = os.path.relpath(v, project)
        if info["hdr"]:
            bad.append(f"{rel} ({info['trc']}/{info['primaries']})")
        if v.endswith(".webm"):
            if not info["alpha"]:
                alpha_lost.append(rel)
                continue
            m = re.search(r'<video[^>]*src="' + re.escape(rel) + r'"[^>]*>', html)
            if m and render and os.path.exists(render):
                st = re.search(r'data-start="([\d.]+)"', m.group(0))
                du = re.search(r'data-duration="([\d.]+)"', m.group(0))
                if st and du:
                    t = float(st.group(1)) + float(du.group(1)) / 2
                    a, b = _frame(render, t), _frame(os.path.join(project, "assets", "aroll.mp4"), t)
                    if a is not None and b is not None:
                        d = float(abs(a - b).mean())
                        probes.append(f"{rel} @{t:.1f}s diff {d:.1f}")
                        if d < 3.0:
                            alpha_lost.append(f"{rel} renders opaque (diff {d:.1f} vs plate)")
    ok = not bad and not alpha_lost
    return _check("hdr_alpha", ok, f"{len(vids)} videos: {len(bad)} HDR-tagged{': ' + ', '.join(bad) if bad else ''}; "
                  f"alpha problems {alpha_lost or 'none'}" + (f"; cut-out probes {', '.join(probes)}" if probes else ""))


TOKENS = {"expo.out", "power4.out", "back.out(1.4)", "back.out(2.2)", "power4.out", "sine.inOut", "power2.inOut",
          "power2.out", "expo.inOut", "power3.in", "power2.in", "elastic.out(1,0.45)", "none"}
FT = re.compile(r"fromTo\(\s*([^,]+?),\s*(\{[^{}]*\})\s*,\s*(\{[^{}]*\})")
EASE_RE = re.compile(r"""["']?ease["']?\s*:\s*["']([^"']+)["']""")


def ease_lint(html_text):
    js = "\n".join(re.findall(r"<script>(.*?)</script>", html_text, re.S))
    bad, entr, raw, opacity_only = [], 0, 0, []
    heroes = set(re.findall(r'id="([^"]+)"[^>]*data-hero', html_text))
    for m in FT.finditer(js):
        sel, frm, to = m.group(1), m.group(2), m.group(3)
        if not re.search(r"""["']?(autoAlpha|opacity)["']?\s*:\s*0(?![.\d])""", frm):
            continue
        entr += 1
        e = EASE_RE.search(to)
        ease = e.group(1) if e else "power1.out"   # GSAP default
        if M.BAD_ENTRANCE.match(ease.strip()):
            bad.append(f"{sel.strip()[:40]} {ease}")
        if ease not in TOKENS:
            raw += 1
        keys = set(re.findall(r"""["']?([A-Za-z]+)["']?\s*:""", frm)) - {"immediateRender"}
        if keys <= {"autoAlpha", "opacity"} and any(h in sel for h in heroes):
            opacity_only.append(sel.strip()[:40])
    return {"entrances": entr, "bad": bad, "raw_eases": raw, "opacity_only_hero": opacity_only}


def check_ease_lint(project, index="index.html", level="polished"):
    p = os.path.join(project, index)
    if not os.path.exists(p):
        return _check("ease_lint", True, "no composition found", True)
    r = ease_lint(open(p, encoding="utf-8").read())
    ok = not r["bad"] and not r["opacity_only_hero"]
    if level == "simple":
        return _check("ease_lint", True, f"{r['entrances']} entrances, {len(r['bad'])} on a crawl curve (simple: info)", True)
    return _check("ease_lint", ok, f"{r['entrances']} entrances: {len(r['bad'])} on a linear/ease-in curve"
                  f"{' (' + '; '.join(r['bad'][:5]) + ')' if r['bad'] else ''}, {len(r['opacity_only_hero'])} opacity-only hero "
                  f"entrances, {r['raw_eases']} raw ease names outside the motion tokens (info)")


GRAPHIC_KINDS = {"card", "insert", "text", "title", "image", "video", "panel", "glyph", "polaroid"}


def check_hero_scale(graphic_beats, tg):
    """graphic_beats: [{t0, t1, boxes:[{kind,x,y,w,h}]}] (captions and faces excluded by the caller or here)."""
    need = tg.get("hero_min_w")
    rows, small = [], []
    for b in graphic_beats:
        gb = [x for x in b.get("boxes", []) if x.get("kind") in GRAPHIC_KINDS]
        if not gb:
            continue
        # union of the beat's graphics: a hero made of several parts (a chart and its labels) counts as one object
        x0, x1 = min(x["x"] for x in gb), max(x["x"] + x["w"] for x in gb)
        w = max(max(x["w"] for x in gb), x1 - x0)
        if b.get("layout") == "media":
            w = 1080      # full-frame media (B-roll) is the hero
        rows.append((b["t0"], w))
        if need and w < need * 1080:
            small.append(f"{b['t0']:.1f}s {int(w)}px")
    if not need:
        return _check("hero_scale", True, f"{len(rows)} graphic beats (simple: exempt)", True)
    return _check("hero_scale", not small, f"{len(rows)} graphic beats, {len(small)} with a hero under "
                  f"{int(need * 100)}% of the width ({int(need * 1080)}px)" + (f": {', '.join(small[:8])}" if small else ""))


def split_graphic_beats(lb):
    """layout_boxes.json -> one entry per insert beat (all its graphic boxes over its whole life, so a chart and the
    labels it grows count as one hero). Persistent overlays (titles, lists) are not a beat's hero. A full-frame media
    beat (B-roll) is its own hero."""
    by = {}
    for qb in lb.get("beats", []):
        for x in qb.get("boxes", []):
            if x.get("beat") and x.get("kind") not in ("caption", "face"):
                by.setdefault(x["beat"], {"t0": x["t0"], "t1": x["t1"], "layout": qb.get("layout"), "boxes": []})
                e = by[x["beat"]]
                e["t0"], e["t1"] = min(e["t0"], x["t0"]), max(e["t1"], x["t1"])
                e["boxes"].append(x)
    for ins in lb.get("inserts", []):
        if ins.get("layout") == "media" and ins.get("inserts"):
            by.setdefault(ins["id"], {"t0": ins["t0"], "t1": ins["t1"], "layout": "media", "boxes": []})["layout"] = "media"
    out = sorted(by.values(), key=lambda b: b["t0"])
    for b in out:
        if b["layout"] == "media" and not b["boxes"]:
            b["boxes"] = [{"kind": "insert", "x": 0, "y": 0, "w": 1080, "h": 1920}]
    return out


def check_sfx_sync(project, sfx_report=None):
    rep = sfx_report or _load(os.path.join(project, "work", "motion_sfx.json"))
    if not rep or rep.get("mode") in (None, "off") or not rep.get("placed"):
        return _check("sfx_sync", True, f"no motion SFX placed (mode {(rep or {}).get('mode', 'off')})", True)
    stem = rep.get("stem") or os.path.join(project, "work", "motion_sfx_stem.wav")
    off = []
    if not os.path.exists(stem):
        return _check("sfx_sync", False, f"{len(rep['placed'])} SFX placed but the SFX stem is missing ({stem}): re-render")
    if os.path.exists(stem):
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", stem, "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                             capture_output=True).stdout
        x = np.frombuffer(raw, np.float32)
        w = 480
        for p in rep["placed"]:
            win = 2.0 / FPS + 0.03     # the tolerance plus a margin: a neighbouring sound in full mode is >= 0.18 s away
            a, b = int(max(0, p["t"] - win) * 48000), int((p["t"] + win) * 48000)
            seg = x[a:b] ** 2
            if len(seg) <= w:
                continue
            c = np.convolve(seg, np.ones(w), "valid")
            pk = (a + int(np.argmax(c)) + w // 2) / 48000
            if abs(pk - p["t"]) > 2.0 / FPS + 0.004:
                off.append(f"{p['sound']} @{p['t']:.2f}s peaks at {pk:.2f}s")
    under = rep.get("under_voice_db")
    ok = not off and (under is None or under >= 17.9)
    return _check("sfx_sync", ok, f"{len(rep['placed'])} SFX ({rep['mode']}): {len(off)} off their event by > 2 frames"
                  f"{' (' + '; '.join(off[:5]) + ')' if off else ''}; loudest SFX moment {under} dB under the voice (floor 18)")


def check_behind_head(plan):
    items = (plan or {}).get("behind", [])
    if not items:
        return _check("behind_head", True, "no behind-head words in this cut", True)
    bad = []
    for b in items:
        x, y, w, h = b["box"]
        hx, hy, hw, hh = b.get("head") or (0, 0, 0, 0)
        ov = max(0, min(x + w, hx + hw) - max(x, hx)) if (min(y + h, hy + hh) > max(y, hy)) else 0
        letters = ov / max(1.0, w / max(1, b.get("chars", 1)))
        if b.get("hidden_letters") is not None:   # measured on the cut-out matte at compose time (exact silhouette)
            letters = b["hidden_letters"]
        if letters > 2.0:
            bad.append(f"'{b.get('text', '')}' @{b['t0']:.1f}s head hides {letters:.1f} letters")
    return _check("behind_head", not bad, f"{len(items)} behind-head words, {len(bad)} with more than 2 letters hidden"
                  + (f": {'; '.join(bad)}" if bad else ""))


def check_transition_budget(plan, total):
    every = (plan or {}).get("transitions", [])
    tr = [t for t in every if not t.get("override")]     # a transition the user asked for is never "too many"
    cfg = (plan or {}).get("config", {})
    lvl = (plan or {}).get("level", "polished")
    per10 = cfg.get("per10s") or 0
    cap = int(per10 * total / 10 + 1) if lvl != "showreel" else 10 ** 6
    win = (plan or {}).get("cutout_windows", [])
    inside = [t["t"] for t in tr if any(a - 0.05 <= t["t"] <= b + 0.05 for a, b in win)]
    gaps = [round(b["t"] - a["t"], 2) for a, b in zip(tr, tr[1:])]
    tight = [g for g in gaps if lvl == "polished" and g < 10.0 / max(per10, 0.1) - 0.05]
    ok = len(tr) <= cap and not inside and not tight
    return _check("transition_budget", ok, f"{len(every)} transitions ({', '.join(t['move'] for t in every) or 'none'}; "
                  f"{len(every) - len(tr)} asked for per beat) for "
                  f"{total:.1f}s at {lvl} (budget {cap if cap < 10 ** 6 else 'every cut'}); {len(inside)} inside a cut-out "
                  f"window; {len(tight)} closer than the budget spacing")


def strips(render, plan, qa_dir, extra_times=(), max_n=8):
    """12 fps strips: 0.5 s before to 0.75 s after each transition (+ extra hero times), 15 tiles each."""
    from PIL import Image, ImageDraw
    times = [(t["t"], t["move"]) for t in (plan or {}).get("transitions", [])][:max(1, max_n - len(extra_times))]
    times = sorted(times + [(t, "hero") for t in extra_times])[:max_n]
    out = []
    for i, (t, what) in enumerate(times):
        t0 = max(0.0, t - 0.5)
        tw, th = 144, 256
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", render, "-t", "1.25", "-vf",
                              f"fps=12,scale={tw}:{th}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        n = len(raw) // (tw * th * 3)
        if not n:
            continue
        sheet = Image.new("RGB", (n * tw, th + 22), (16, 16, 18))
        d = ImageDraw.Draw(sheet)
        for k in range(n):
            im = Image.frombytes("RGB", (tw, th), raw[k * tw * th * 3:(k + 1) * tw * th * 3])
            sheet.paste(im, (k * tw, 22))
            d.text((k * tw + 4, 5), f"{t0 + k / 12:.2f}", fill=(220, 220, 220))
        d.text((4, 5), f"{what} @{t:.2f}s", fill=(255, 200, 80))
        p = os.path.join(qa_dir, f"motion_strip_{i:02d}.jpg")
        sheet.save(p, quality=85)
        out.append(p)
    return out


# ---------------------------------------------------------------------------------------------- runner
def run(project, render, qa_dir=None, level=None, graphic_beats=None, extra_events=(), index="index.html",
        only=None, words=None, total=None):
    """-> list of check dicts. Also writes <qa_dir>/motion.json."""
    project = os.path.abspath(project)
    qa_dir = qa_dir or os.path.join(project, "qa")
    os.makedirs(qa_dir, exist_ok=True)
    plan = M.load_plan(project) or {}
    pj = _load(os.path.join(project, "project.json"), {})
    cfg = M.config(pj, {"level": level} if level else None)
    lvl = level or plan.get("level") or cfg["level"]
    tg = dict(M.LEVELS[lvl]["targets"])
    if (pj.get("motion") or {}).get("still_max") is not None:
        tg["still_max"] = float(pj["motion"]["still_max"])
    if pj.get("motion") is False or (not plan and "motion" not in pj):
        why = "motion layer off for this project (motion: false)" if pj.get("motion") is False else \
            "no motion plan (composed before Motion v2): re-compose to apply the motion gates"
        return [_check(n, True, why, True) for n in (only or NAMES)]
    words = words if words is not None else _load(os.path.join(project, "words.json"), [])
    want = set(only or NAMES)
    m = metrics(render) if want & {"motion_density", "dead_frames"} else None
    total = total or (m["dur"] if m else (plan.get("frames", 0) / FPS))
    if graphic_beats is None:
        graphic_beats = split_graphic_beats(_load(os.path.join(project, "layout_boxes.json"), {}))
    checks = []
    spans = plan.get("levels") or []
    groups = level_groups(spans, cfg if not level else M.config(pj, {"level": lvl}), pj) \
        if len({x[2] for x in spans}) > 1 and not level else None
    if "motion_density" in want:
        checks.append(check_motion_density_levels(m, groups) if groups else check_motion_density(m, tg))
    if "dead_frames" in want:
        checks.append(check_dead_frames_levels(m, groups) if groups else check_dead_frames(m, tg))
    if "event_density" in want:
        checks.append(check_event_density_levels(plan, words, groups, extra_events) if groups
                      else check_event_density(plan, words, tg, total, extra_events))
    if "hdr_alpha" in want:
        checks.append(check_hdr_alpha(project, render, index))
    if "ease_lint" in want:
        checks.append(check_ease_lint(project, index, lvl))
    if "hero_scale" in want:
        checks.append(check_hero_scale(graphic_beats, tg))
    if "sfx_sync" in want:
        checks.append(check_sfx_sync(project))
    if "behind_head" in want:
        checks.append(check_behind_head(plan))
    if "transition_budget" in want:
        checks.append(check_transition_budget(plan, total))
    if "motion_strips" in want:
        try:
            heroes = [b["t0"] for b in sorted(graphic_beats, key=lambda b: -max([x.get("w", 0) for x in b.get("boxes", [])] or [0]))][:3]
            ps = strips(render, plan, qa_dir, extra_times=heroes)
            checks.append(_check("motion_strips", True, f"{len(ps)} strips at 12 fps: " + ", ".join(os.path.basename(p) for p in ps)))
        except Exception as e:  # noqa: BLE001
            checks.append(_check("motion_strips", False, f"could not write the strips: {e}"))
    out = {"level": lvl, "levels": spans, "targets": tg, "metrics": {k: v for k, v in (m or {}).items() if k != "d"} if m else None, "sparkline": spark(m["persec"]) if m else "",
           "events": visual_events(plan, extra_events), "checks": checks}
    with open(os.path.join(qa_dir, "motion.json"), "w") as f:
        json.dump(out, f, indent=1)
    return checks


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    opt = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None  # noqa: E731
    if opt("--level") and opt("--level") not in M.LEVELS:
        raise SystemExit(f"--level must be one of {', '.join(M.LEVELS)}")
    out = opt("--out")
    args = [a for a in args if a not in (out, opt("--level"))]
    checks = run(args[0], os.path.abspath(args[1]), out, opt("--level"))
    if "--json" in argv:
        print(json.dumps(checks, indent=1))
    else:
        for c in checks:
            tag = "SKIP" if c.get("skipped") else ("PASS" if c["pass"] else "FAIL")
            print(f"{tag}  {c['name']:<17} {c['label']}: {c['detail']}")
    sys.exit(0 if all(c["pass"] for c in checks) else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
