"""motionlayer.py: wires the engine motion system (engine/motion) into the split engine's composition.

compose.py calls:
  mcfg = motionlayer.config(project, pj)                     before the inserts render (eases upgrade through Ctx)
  mv   = motionlayer.build(project, cx, mcfg, ...)            after beats + captions: camera rig, transitions, events
and passes mv["page"] to page.build_html.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOTION_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "engine", "motion")
if MOTION_DIR not in sys.path:
    sys.path.insert(0, MOTION_DIR)
import motion as M  # noqa: E402

FPS = 30
STOP = set("a an the and or but so to of in on at for with is are was were be been it its this that these those you your "
           "i me my we our they them he she his her do does did not no yes if then than as by from up out about into just "
           "can will would could should have has had there here what which who how when where why".split())


def config(project, pj):
    return M.config(pj)


def auto_accents(words, n_target):
    """Emphasis words when the project names none: numbers, then sentence-final content words (the payoff)."""
    out = []
    for i, w in enumerate(words):
        t = w["text"]
        n = M._norm(t)
        if not n or n in STOP:
            continue
        if re.search(r"\d", n) or (re.search(r"[.!?]$", t) and len(n) >= 4):
            out.append(n)
    return out[: max(1, n_target)]


def _overrides(edl):
    return {e["id"]: (e.get("motion") or {}) for e in edl}


def _shots(placement, facepos, edl_ov):
    shots = []
    for p in placement:
        fp = facepos.get(p["seg"]) or {}
        key = (p["seg"], p["layout"], p["visible"], p["scale"], p["dx"], p["dy"])
        if shots and shots[-1]["_key"] == key and abs(shots[-1]["t1"] - p["t0"]) < 1e-3:
            shots[-1]["t1"] = p["t1"]
            continue
        shots.append({"_key": key, "t0": p["t0"], "t1": p["t1"], "seg": p["seg"], "layout": p["layout"],
                      "visible": bool(p["visible"]) and p["layout"] not in ("stage", "media"),
                      "ox": float(fp.get("cx", 540)), "oy": float(fp.get("cy", 900)), "face_h": float(fp.get("h", 300)),
                      "face": p.get("face"), "override": edl_ov.get(p["seg"], {})})
    return shots


def _cuts(shots, beats, edl_ov):
    def beat_at(t):
        return next((b for b in beats if b["t0"] - 1e-4 <= t < b["t1"] - 1e-4), None)
    out = []
    for a, b in zip(shots, shots[1:]):
        t = b["t0"]
        ba, bb = beat_at(t - 1e-3), beat_at(t + 1e-3)
        sig = lambda x: (x["layout"], json.dumps(x["items"], sort_keys=True)) if x else None  # noqa: E731
        section = (a["layout"] != b["layout"]) or (sig(ba) != sig(bb) and bb is not None and bb.get("items"))
        face = b.get("face") or a.get("face")
        out.append({"t": t, "section": bool(section), "visible": a["visible"] or b["visible"], "into": b["seg"],
                    "level": (edl_ov.get(b["seg"]) or {}).get("level"),
                    "jump": a["seg"] != b["seg"], "override": edl_ov.get(b["seg"], {}) if a["seg"] != b["seg"] else {},
                    "point": [face["cx"], face["cy"]] if face else None})
    return out


def behind_head(project, cx, specs, shots, placement, words, frames, brand):
    """project.json motion.behind: [{"text", "at": "@word"|s, "until": "@word"|s, "size": 200, "color": "accent"}]
    A word BEHIND the speaker's head: text layer on the camera, the live cut-out (assets/aroll_matte.webm, VP9 alpha,
    from engine/cutout.py) above it, both inside the camera so they move with every punch and push. The cut-out only
    plays inside each word's window (never across a cut). -> (html, js, plan items, cut-out windows)."""
    if not specs:
        return "", [], [], []
    import layouts as lay
    matte = os.path.join(project, "assets", "aroll_matte.webm")
    if not os.path.exists(matte):
        cx.warn("motion.behind needs assets/aroll_matte.webm (run engine/cutout.py); behind-head words skipped")
        return "", [], [], []
    html, js, items, wins = [], [], [], []
    track = 60
    for i, b in enumerate(specs):
        cur = M.WordCursor(words)
        t0 = cur.at(b["at"], lead="type") if isinstance(b["at"], str) else float(b["at"])
        cur.pos = max(cur.pos, t0 + 0.01)        # "until" is searched after the word starts
        sh = next((x for x in shots if x["t0"] - 1e-3 <= t0 < x["t1"] and x["visible"]), None)
        if not sh:
            cx.warn(f"behind-head word '{b['text']}' at {t0:.2f}s has no visible speaker; skipped")
            continue
        t1 = cur.at(b["until"], lead="none") if isinstance(b.get("until"), str) else float(b.get("until", t0 + 1.6))
        t1 = min(t1, sh["t1"])                       # never across a cut
        f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
        if f1 - f0 < 6:
            continue
        fp = sh
        size = int(b.get("size", 200))
        mid = (t0 + t1) / 2
        head_top, alpha = head_from_matte(project, mid, fp["ox"], fp["face_h"])
        if head_top is None:                                    # no readable matte frame: estimate from the face box
            head_top = fp["oy"] - 0.8 * fp["face_h"]
        top = round(head_top + 0.3 * size - size)               # the head breaks the foot of the word (~30 %)
        col = brand.get("colors", {}).get(b.get("color", "accent"), b.get("color", "#7A1E2E"))
        fam = brand.get("fonts", {}).get("display", "Inter Tight")
        wid = f"mvBh{i}"
        w_est = min(960, size * 0.62 * len(b["text"]))
        room = max(0.0, 540 - 60 - w_est / 2)
        shift = round(max(-room, min(room, fp["ox"] - 540)))   # centred on the head when the frame allows it
        html.append(f'<div class="mv-behind" id="{wid}" style="top:{top}px;left:{shift}px"><span class="w" data-mfit="960" '
                    f'style="font:900 {size}px/1 \'{fam}\',sans-serif;color:{col}">{cx_esc(b["text"])}</span></div>')
        dur = (f1 - f0 + 3) / FPS                    # coverage gate: the layer outlives its window by 3 frames
        html.append(f'<div class="mv-vid" id="mvCut{i}"><video id="mvCutV{i}" src="assets/aroll_matte.webm" muted playsinline '
                    f'data-start="{f0 / FPS:.5f}" data-media-start="{f0 / FPS:.5f}" data-duration="{dur:.5f}" '
                    f'data-track-index="{track + i}"></video></div>')
        js.append(f"tl.set('#mvCut{i}',{{autoAlpha:1}},{(f0 - 0.5) / FPS:.5f});tl.set('#mvCut{i}',{{autoAlpha:0}},{(f1 - 0.5) / FPS:.5f});")
        js.append(f"tl.set('#{wid}',{{autoAlpha:1}},{(f0 - 0.5) / FPS:.5f});")
        js.append(f"RRM.enter('letters',tl,document.querySelector('#{wid} .w'),{(f0 - 0.5) / FPS:.5f},{{stagger:0.028,dur:0.46}});")
        js.append(f"tl.set('#{wid}',{{autoAlpha:0}},{(f1 - 0.5) / FPS:.5f});")
        # screen-space boxes for QA (behind_head): word estimate + head box through the layout placement
        pl = next((p for p in placement if p["t0"] - 1e-3 <= t0 < p["t1"]), None)
        cxw = 540 + shift
        x0, y0 = lay.map_pt(pl, cxw - w_est / 2, top) if pl else (cxw - w_est / 2, top)
        x1, y1 = lay.map_pt(pl, cxw + w_est / 2, top + size) if pl else (cxw + w_est / 2, top + size)
        hx0, hy0 = lay.map_pt(pl, fp["ox"] - 0.65 * fp["face_h"], head_top) if pl else (0, 0)
        hx1, hy1 = lay.map_pt(pl, fp["ox"] + 0.65 * fp["face_h"], fp["oy"] + 0.8 * fp["face_h"]) if pl else (0, 0)
        hidden = None
        if alpha is not None:   # letters the head really covers: silhouette columns inside the word's band (aroll px)
            k = 1080 / alpha.shape[1]
            band = alpha[int(max(0, top) / k):int(max(0, top + size) / k), :] > 128
            colmask = band.any(axis=0)
            wx0, wx1 = int((cxw - w_est / 2) / k), int((cxw + w_est / 2) / k)
            covered = float(colmask[max(0, wx0):max(0, wx1)].sum() * k)
            hidden = round(covered / max(1.0, w_est / len(b["text"])), 2)
        items.append({"text": b["text"], "t0": round(t0, 3), "t1": round(t1, 3), "chars": len(b["text"]),
                      **({"hidden_letters": hidden} if hidden is not None else {}),
                      "box": [round(x0), round(y0), round(x1 - x0), round(y1 - y0)],
                      "head": [round(hx0), round(hy0), round(hx1 - hx0), round(hy1 - hy0)]})
        wins.append((round(f0 / FPS, 3), round(f1 / FPS, 3)))
        cx.event(t0, "stamp", f"behind-head {b['text']}")
    return "\n".join(html), js, items, wins


def matte_alpha(project, t, w=540, h=960):
    """Alpha plane of the cut-out at time t (VP9 alpha needs the libvpx decoder), as a uint8 array h x w, or None."""
    import subprocess
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.3f}", "-i",
                        os.path.join(project, "assets", "aroll_matte.webm"), "-frames:v", "1", "-vf",
                        f"alphaextract,scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if len(p.stdout) != w * h:
        return None
    return np.frombuffer(p.stdout, np.uint8).reshape(h, w)


def head_from_matte(project, t, ox, face_h):
    """(head_top, alpha) in aroll px: the top of the speaker's silhouette over the face column, measured on the matte."""
    a = matte_alpha(project, t)
    if a is None:
        return None, None
    k = 1080 / a.shape[1]
    c0, c1 = int(max(0, (ox - 0.35 * face_h) / k)), int(min(a.shape[1], (ox + 0.35 * face_h) / k))
    rows = (a[:, c0:c1] > 128).any(axis=1).nonzero()[0]
    return (float(rows[0] * k) if len(rows) else None), a


def calm_caption_js(i, t):
    """A calm caption entrance: the chunk fades in and rises 12 px over 8 frames (settle ease). No scale, no pop."""
    t = max(0.0, (round(t * FPS) - 0.5) / FPS)
    return (f"tl.fromTo('#c{i} .pill',{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.26,ease:RRM.EASE.settle,"
            f"immediateRender:false}},{t:.5f});")


def deck_caption_js(i, t):
    import deck
    return deck.caption_js(i, t)


def cx_esc(t):
    import html as _h
    return _h.escape(str(t), quote=True)


def build(project, cx, mcfg, *, placement, facepos, beats, edl, words, chunks, cap_cfg, frames, brand, pj=None):
    edl_ov = _overrides(edl)
    for sid, ov in (getattr(cx, "cut_motion", None) or {}).items():   # a style's per-cut camera asks (edl.json wins)
        edl_ov[sid] = {**ov, **edl_ov.get(sid, {})}
    shots = _shots(placement, facepos, edl_ov)
    cuts = _cuts(shots, beats, edl_ov)
    for c in cuts:   # a style can mark cuts that open a new section (list-stack: a new list item lands on that cut)
        if c["into"] in (getattr(cx, "section_cuts", None) or ()):
            c["section"] = True
    bh_html, bh_js, bh_items, bh_wins = behind_head(project, cx, ((pj or {}).get("motion") or {}).get("behind"),
                                                    shots, placement, words, frames, brand)
    accents = [a.lower() for a in (cap_cfg.get("accent") or [])]
    if not accents and mcfg["punch"] > 1.0:
        accents = auto_accents(words, int(frames / FPS / 2.5))
    for w in getattr(cx, "deck_accents", None) or []:     # split-deck: the speaker punches with the panel's hits
        if w not in accents:
            accents.append(w)
    g_events = sorted({round(e["t"], 3) for e in cx.events} |
                      {round(b["t0"], 3) for b in beats if b.get("items")})
    strong = sorted({round(b["t0"], 3) for b in beats if b.get("items")} |
                    {round(e["t"], 3) for e in cx.events if e.get("kind") in ("whoosh", "flip", "thud")})
    alive = None
    aroll = os.path.join(project, "assets", "aroll.mp4")
    if os.path.exists(aroll) and mcfg.get("fill_gap"):
        diff = M.plate_activity(aroll, frames, os.path.join(project, "work", "plate_activity.json"))
        alive = M.alive_from(diff, shots, frames)
    plan = M.plan(frames=frames, cuts=cuts, shots=shots, words=words, accents=accents, graphic_events=g_events,
                  cfg=mcfg, alive=alive, strong_events=strong, cutout_windows=bh_wins, log=print)
    script, grain = M.ensure_assets(project, mcfg)
    cam_sel = ",".join(["#mvCam"] + list(getattr(cx, "cam_followers", None) or []))   # plate copies (head bubble)
    js = ["RRM.fitAll();"] + M.emit_js(plan, cam_sel=cam_sel, words=words) + M.grain_js(mcfg, frames) + bh_js
    # kinetic captions: every caption chunk enters (rise), payoff words stamp
    acc = {M._norm(a) for a in accents}
    shown = [c for c in chunks if not c.get("hidden")]
    kinds = []
    for i, c in enumerate(shown):
        if cap_cfg.get("calm"):            # calm captions (kallaway preset): every chunk fades and rises, no pops
            js.append(calm_caption_js(i, c["t0"]))
            kinds.append("calm")
            continue
        k = M.caption_kind(c["text"], acc, M.for_level(mcfg, M.level_at(plan, c["t0"])), i)   # the beat's own level
        kinds.append(k)
        if k == "rise" and getattr(cx, "deck", False) and c.get("layout") == "split":
            js.append(deck_caption_js(i, c["t0"]))        # seam pill snaps in (deck.py)
        elif k:
            js.append(f"RRM.capIn(tl,'#c{i} .pill',{max(0.0, (round(c['t0'] * FPS) - 0.5) / FPS):.5f},'{k}');")
            if k in ("stamp", "grow"):
                plan["events"].append({"t": round(c["t0"], 3), "kind": "type", "what": c["text"], "src": "motion"})
    plan["events"].sort(key=lambda e: e["t"])
    iris = brand.get("colors", {}).get("ink", "#0C0C0F")
    page = {"script": script, "css": M.css(mcfg, iris), "defs": M.DEFS_HTML, "top": M.top_layers_html(mcfg, grain),
            "vignette": bool(mcfg.get("vignette")), "behind": bh_html}
    plan["behind"], plan["cutout_windows"] = bh_items, bh_wins
    plan["cuts"] = [{k: v for k, v in c.items() if k != "override"} for c in cuts]
    plan["shots"] = [{k: v for k, v in s.items() if not k.startswith("_") and k != "override"} for s in shots]
    plan["graphic_events"] = [{"t": e["t"], "kind": e["kind"], "what": e.get("what", "")} for e in cx.events]
    plan["captions"] = {"kinetic": sum(1 for k in kinds if k and k != "calm"), "stamps": sum(1 for k in kinds if k in ("stamp", "grow"))}
    if "calm" in kinds:
        plan["captions"]["calm"] = kinds.count("calm")
    plan["accents"] = accents
    M.write_plan(project, plan)
    return {"js": js, "page": page, "plan": plan}
