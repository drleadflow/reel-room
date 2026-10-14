"""stylekit: shared plumbing for the full-frame style templates (floating-cards, carousel-slideup, desk-demo).

One composition = one paused GSAP timeline over a full-frame speaker video. This module owns:
  project loading (project.json, brand.json, words.json, segments.json), word anchors ("@panel", "@fasting:2+0.1"),
  a tween emitter that snaps every event onto its frame, the index.html page (fonts, gsap, measuring runtime),
  timeline sampling in headless Chrome (every element's on-screen box every N frames, transforms included),
  lint + render through the pinned HyperFrames, and the sound pass (voice untouched + SFX cues + -14 LUFS master).
It reuses the split template's theme/measure/render helpers and the engine's deliver.make_master; it never edits them.
"""
import html as _html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.dirname(HERE)
SPLIT = os.path.join(TEMPLATES, "split")
ENGINE = os.path.join(os.path.dirname(TEMPLATES), "engine")
for p in (SPLIT, ENGINE, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import theme  # noqa: E402  (split template: brand + fonts)
MOTION_DIR = os.path.join(ENGINE, "motion")
if MOTION_DIR not in sys.path:
    sys.path.insert(0, MOTION_DIR)
import motion as M  # noqa: E402  (engine motion v2: camera rig, transitions, events)

_CUR = {"proj": None, "tl": None, "cfg": None, "overrides": None, "cuts": None}   # the composition being built (one per process);
# overrides: {seg id: {"transition": "whip" | "none", "camera": ...}} a template's per-segment motion defaults
# cuts: [{"frame": N, "transition": "whip" | "none"}] picture cuts a template makes inside a segment (desk-demo cutaways)
import measure as _measure  # noqa: E402  (split template: headless chrome finder)
from timeline import Words  # noqa: E402

FPS = 30
W, H = 1080, 1920
SAFE = {"top": 220, "bottom": 1470, "side": 35, "right_x": 980, "right_from": 1155}
GSAP_VER = "3.14.2"
GSAP_CDN = f"https://cdn.jsdelivr.net/npm/gsap@{GSAP_VER}/dist/gsap.min.js"
EM_DASHES = "\u2014\u2013\u2015"


# ----------------------------------------------------------------------------- basics
def jload(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if default is None:
        raise SystemExit(f"missing {path}")
    return default


def jsave(path, data, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def esc(s):
    return _html.escape(str(s), quote=True)


def frame_of(t):
    return int(round(t * FPS))


def snap(t):
    """Timeline time for an event meant to land ON frame N = round(t*FPS): half a frame early, so frame N sees it."""
    return max(0.0, round((round(t * FPS) - 0.5) / FPS, 5))


def fsnap(n):
    """Same as snap() for an explicit frame number."""
    return max(0.0, round((n - 0.5) / FPS, 5))


def duration_str(frames):
    """Seconds string such that ceil(d * FPS) == frames (HyperFrames renders ceil)."""
    ms = frames * 1000 // FPS
    while -(-ms * FPS // 1000) != frames:
        ms -= 1
    return f"{ms // 1000}.{ms % 1000:03d}"


def run(cmd, cwd=None, timeout=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(map(str, cmd))[:300]}\n{(p.stderr or '')[-1500:]}")
    return p


def probe(path):
    out = run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate,nb_read_frames:format=duration", "-of", "json", path]).stdout
    d = json.loads(out)
    s = d["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    return {"w": s["width"], "h": s["height"], "fps": num / den, "frames": int(s.get("nb_read_frames", 0)),
            "dur": float(d["format"]["duration"])}


# ----------------------------------------------------------------------------- project
class Project:
    def __init__(self, project_dir):
        self.dir = os.path.abspath(project_dir)
        self.pj = jload(self.p("project.json"), {})
        self.brand = theme.load_brand(self.dir)
        self.words_raw = jload(self.p("words.json"))
        self.words = Words(self.words_raw)
        self.segments = jload(self.p("segments.json"), [])
        self.style = self.pj.get("style_cfg", {})
        self.motion = None if self.pj.get("motion") is False else M.config(self.pj)
        _CUR["proj"], _CUR["cfg"], _CUR["overrides"] = self, self.motion, None
        _CUR["cuts"] = None

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    @property
    def colors(self):
        return self.brand["colors"]

    @property
    def fonts(self):
        return self.brand["fonts"]

    def at(self, spec, lo=0.0, hi=None):
        """'@word[:n][+/-off]' or a number (cut seconds) -> cut seconds of that word's start."""
        if isinstance(spec, (int, float)):
            return float(spec)
        if ">" in str(spec):  # '@word>segid': first match inside that segment
            spec, sid = str(spec).split(">", 1)
            seg = next((s for s in self.segments if s["id"] == sid), None)
            if seg is None:
                raise SystemExit(f"unknown segment '{sid}' in anchor")
            lo = max(lo, seg["frame"] / FPS - 0.02)
            hi = (seg["frame"] + seg["frames"]) / FPS
        m = re.match(r"^@?(.+?)(?::(\d+))?(?:([+-]\d*\.?\d+))?$", str(spec).strip())
        key = m.group(1) + (f":{m.group(2)}" if m.group(2) else "")
        t = self.words.find(key, lo, hi)
        if t is None:
            raise SystemExit(f"word anchor {spec!r} not found after {lo:.2f}s")
        return t + float(m.group(3) or 0)

    def word_end(self, spec, lo=0.0):
        t = self.at(spec, lo)
        for w in self.words_raw:
            if abs(float(w["start"]) - t) < 1e-6:
                return float(w["end"])
        return t


# ----------------------------------------------------------------------------- timeline emitter
class TL:
    """Collects GSAP calls (all snapped to frames), QA events and SFX cues."""

    def __init__(self):
        self.js, self.events, self.cues = [], [], []
        _CUR["tl"] = self

    def set(self, sel, t, vars_):
        self.js.append(f"tl.set({json.dumps(sel)},{json.dumps(vars_)},{snap(t)});")

    def fromto(self, sel, t, frm, to, dur=0.35, ease="power3.out"):
        if any(frm.get(k) == 0 for k in ("opacity", "autoAlpha")):   # an entrance: motion v2 eases (snap)
            ease = M.upgrade_ease(ease, _CUR["cfg"])
        v = dict(to)
        v.update(duration=dur, ease=ease, immediateRender=False)  # never show the 'from' state before its frame
        self.js.append(f"tl.fromTo({json.dumps(sel)},{json.dumps(frm)},{json.dumps(v)},{snap(t)});")

    def to(self, sel, t, vars_, dur=0.3, ease="power2.out", exact=False):
        v = dict(vars_)
        v.update(duration=dur, ease=ease)
        at = round(t, 5) if exact else snap(t)
        self.js.append(f"tl.to({json.dumps(sel)},{json.dumps(v)},{at});")

    def keyframes(self, sel, t0, frames):
        """frames: list of dicts (x,y,rotation,scale...) one per video frame from t0; stepped exactly per frame."""
        step = 1.0 / FPS
        base = snap(t0)
        for i, fr in enumerate(frames):
            self.js.append(f"tl.set({json.dumps(sel)},{json.dumps(fr)},{round(base + i * step, 5)});")

    def raw(self, line):
        self.js.append(line)

    def event(self, t, kind, label, region=None, frame=None, sel=None, show=None):
        """kind: 'cut' (hard switch, must change exactly on this frame) or 'enter' (visible from this frame).
        sel + show: the element (#id) that must be hidden on frame N-1 and visible on N (show=True) or the reverse."""
        self.events.append({"frame": frame if frame is not None else frame_of(t), "kind": kind, "label": label,
                            "region": region, "sel": sel, "show": show})

    def cue(self, t, name, gain_db=0.0, frame=None):
        f = frame if frame is not None else frame_of(t)
        self.cues.append({"frame": f, "t": round(f / FPS, 4), "name": name, "gain_db": gain_db})


def box(kind, t0, t1, readable=True, extra=""):
    """kind: card | text | caption | title | cutaway (full-frame insert that replaces the speaker)."""
    r = ' data-readable="1"' if readable else ""
    return f'data-box="{kind}" data-t0="{t0:.3f}" data-t1="{t1:.3f}"{r}{extra}'


# ----------------------------------------------------------------------------- page
RUNTIME = r"""
const RR_MODE = location.hash.slice(1);
function rrRange(el){ const r = document.createRange(); r.selectNodeContents(el); return r; }
function rrFitEl(el){
  const [max, min] = el.dataset.fit.split(',').map(Number);
  if (!el.dataset.base) el.dataset.base = parseFloat(getComputedStyle(el).fontSize);
  let fs = Number(el.dataset.base); el.style.fontSize = fs + 'px';
  for (let i = 0; i < 5; i++) {
    const w = rrRange(el).getBoundingClientRect().width;
    if (w <= max + 0.5 || fs <= (min || 20)) break;
    fs = Math.max(min || 20, fs * (max / w) * 0.995); el.style.fontSize = fs + 'px';
  }
}
function rrFitAll(){ document.querySelectorAll('[data-fit]').forEach(rrFitEl); }
function rrVis(el){
  let op = 1;
  for (let e = el; e && e !== document.body; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none') return 0;
    op *= Number(cs.opacity);
  }
  if (getComputedStyle(el).visibility === 'hidden') return 0;
  return op;
}
function rrBoxes(){
  const root = document.getElementById('root').getBoundingClientRect(), out = [];
  document.querySelectorAll('[data-box]').forEach(el => {
    const op = rrVis(el); if (op < 0.04) return;
    const kind = el.dataset.box, tight = (kind === 'text' || kind === 'caption' || kind === 'title');
    const r = tight ? rrRange(el).getBoundingClientRect() : el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    out.push({id: el.id || null, kind, op: Math.round(op * 100) / 100, readable: el.dataset.readable === '1',
      text: tight ? el.textContent.trim().slice(0, 120) : '', x: Math.round(r.left - root.left), y: Math.round(r.top - root.top),
      w: Math.round(r.width), h: Math.round(r.height)});
  });
  return out;
}
function rrDump(obj){ const pre = document.createElement('pre'); pre.id = 'rr-out'; pre.textContent = JSON.stringify(obj); document.body.appendChild(pre); }
"""


def build_html(*, title, css, fontface, fonts_load, total, body, tween_js, init_js="", gsap_src="assets/gsap.min.js"):
    mv = motion_layer(body, total) if _CUR["proj"] is not None and _CUR["cfg"] else None
    if mv:
        body, css, tween_js = mv["body"], css + mv["css"], tween_js + "\n" + "\n".join("  " + j for j in mv["js"])
        gsap_src_tag = f'<script src="{esc(gsap_src)}"></script>\n<script src="{esc(mv["script"])}"></script>'
    else:
        gsap_src_tag = f'<script src="{esc(gsap_src)}"></script>'
    fl = json.dumps(fonts_load)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={W}, height={H}">
<title>{esc(title)}</title>
{gsap_src_tag}
<style>
{fontface}
{css}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total}">
{body}
</div>
<script>
{RUNTIME}
(async function () {{
  try {{ await Promise.all({fl}.map(f => document.fonts.load(f))); await document.fonts.ready; }} catch (e) {{}}
  rrFitAll();
{init_js}
  const tl = gsap.timeline({{ paused: true }});
{tween_js}
  if (RR_MODE.startsWith('seek:')) {{ const r = document.getElementById('root'); r.style.width = '1080px'; r.style.height = '1920px';
    tl.seek(Number(RR_MODE.slice(5)) / 30, true); return; }}
  if (RR_MODE.startsWith('frames:')) {{
    const res = [];
    for (const f of RR_MODE.slice(7).split(',').map(Number)) {{ tl.seek(f / 30, true); res.push({{f, boxes: rrBoxes(),
      vis: Array.from(document.querySelectorAll('[id]')).filter(e => e.id && e.id !== 'root').map(e => [e.id, Math.round(rrVis(e) * 100) / 100])}}); }}
    rrDump(res); return;
  }}
  if (RR_MODE.startsWith('sample')) {{
    const [_, step, n] = RR_MODE.split(':').map(Number), res = [];
    for (let f = 0; f < n; f += step) {{ tl.seek(f / 30, true); res.push({{f, boxes: rrBoxes()}}); }}
    rrDump(res); return;
  }}
  window.__timelines = window.__timelines || {{}};
  window.__timelines["main"] = tl;
}})();
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------------- motion v2 layer
SPEAKER_VIDEO = re.compile(r'(<video[^>]*\bid="(?:aroll|base)"[^>]*>\s*</video>)')
CAPTION_JS = """document.querySelectorAll('[data-box="caption"]').forEach(function (el) {
    var p = el.parentElement, t0 = Number(el.dataset.t0); if (!p || p.dataset.rrmCap) return; p.dataset.rrmCap = '1';
    if ((typeof RRM_PLAIN !== 'undefined') && RRM_PLAIN.some(function (s) { return t0 >= s[0] - 0.001 && t0 < s[1]; })) return;
    RRM.capIn(tl, p, Number(el.dataset.t0), el.dataset.accent ? 'stamp' : 'rise'); });"""


def _face_by_seg(proj, frames):
    """Median face (cx, cy, h) per segment from the face track (screen px; stylekit plates are full frame)."""
    ft = None
    for name in ("facetrack_screen.json", "facetrack.json"):
        if os.path.exists(proj.p("work", name)):
            ft = jload(proj.p("work", name))
            break
    out = {}
    for s in proj.segments:
        rows = []
        for f in range(s["frame"], s["frame"] + s["frames"]):
            b = (ft or {}).get("boxes", {}).get(str(f))          # stylekit format: [x, y, w, h] top-left
            if b:
                rows.append((b[0] + b[2] / 2, b[1] + b[3] / 2, b[3]))
                continue
            v = (ft or {}).get("faces", {}).get(str(f))          # split format: [cx, cy, h, ok]
            if v and (len(v) < 4 or v[3]):
                rows.append(v)
        if rows:
            rows.sort(key=lambda v: v[0])
            m = rows[len(rows) // 2]
            out[s["id"]] = (float(m[0]), float(m[1]), float(m[2]))
    return out


def motion_layer(body, total):
    """Wrap the speaker <video> (id aroll|base) in #mvT (transitions) > #mvCam (camera rig), plan the camera and the
    transitions from the segments, kinetic caption entrances, and write work/motion_plan.json."""
    proj, tl, cfg = _CUR["proj"], _CUR["tl"], _CUR["cfg"]
    m = SPEAKER_VIDEO.search(body)
    if not m or not proj.segments:
        return None
    frames = sum(s["frames"] for s in proj.segments)
    faces = _face_by_seg(proj, frames)
    shots, cuts = [], []
    ev = (tl.events if tl else [])
    scene_cuts = {e["frame"] for e in ev if e.get("kind") == "cut" and (e.get("region") or [0, 0, 1080, 1920])[2:] == [1080, 1920]}
    zoom = {e["id"]: e.get("zoom", 1.0) for e in jload(proj.p("edl.json"), [])}
    edl_ov = {e["id"]: (e.get("motion") or {}) for e in jload(proj.p("edl.json"), [])}
    for sid, ov in (_CUR.get("overrides") or {}).items():     # a template's own per-segment defaults; the edl wins
        edl_ov[sid] = {**ov, **edl_ov.get(sid, {})}
    for s in proj.segments:
        cx_, cy_, h_ = faces.get(s["id"], (540.0, 760.0, 300.0))
        # full-frame styles hang captions and cards right off the face: grow the head from the chin (captions stay
        # clear) and cap the whole camera at 4.5 %
        shots.append({"t0": s["frame"] / FPS, "t1": (s["frame"] + s["frames"]) / FPS, "seg": s["id"], "layout": "full",
                      "visible": True, "ox": cx_, "oy": cy_ + 0.45 * h_, "face_h": h_,
                      "kmax": float((edl_ov.get(s["id"]) or {}).get("kmax", 1.045)),   # a template may allow more
                      "face": {"cx": cx_, "cy": cy_},
                      "override": edl_ov.get(s["id"], {})})
    for a, b in zip(proj.segments, proj.segments[1:]):
        f = b["frame"]
        sec = any(abs(f - x) <= 2 for x in scene_cuts) or abs(zoom.get(a["id"], 1) - zoom.get(b["id"], 1)) > 0.05
        fc = faces.get(b["id"])
        cuts.append({"t": f / FPS, "section": sec, "visible": True, "into": b["id"], "override": edl_ov.get(b["id"], {}),
                     "level": (edl_ov.get(b["id"]) or {}).get("level"),
                     "point": [fc[0], fc[1]] if fc else None})
    for xc in _CUR.get("cuts") or []:   # a template's own picture cuts INSIDE a segment (screen cutaways): {frame, transition}
        f = int(xc["frame"])
        if any(abs(c["t"] * FPS - f) < 1.5 for c in cuts):
            continue
        sg = next((s for s in proj.segments if s["frame"] <= f < s["frame"] + s["frames"]), None)
        fc = faces.get(sg["id"]) if sg else None
        cuts.append({"t": f / FPS, "section": True, "visible": True, "into": sg["id"] if sg else None,
                     "override": {"transition": xc["transition"]} if xc.get("transition") else {}, "level": None,
                     "point": [fc[0], fc[1]] if fc else None})
    cuts.sort(key=lambda c: c["t"])
    g_events = sorted({round(e["frame"] / FPS, 3) for e in ev})
    # only big changes stop a stretch from reading as still (a row tick or a small pill does not)
    strong = sorted({round(e["frame"] / FPS, 3) for e in ev
                     if e.get("kind") == "cut" or ((e.get("region") or [0, 0, 0, 0])[2] * (e.get("region") or [0, 0, 0, 0])[3]
                                                   >= 0.12 * W * H)})
    vsrc = re.search(r'src="([^"]+)"', m.group(1)).group(1)
    alive = None
    if cfg.get("fill_gap") and os.path.exists(proj.p(vsrc)):
        diff = M.plate_activity(proj.p(vsrc), frames, proj.p("work", "plate_activity.json"))
        alive = M.alive_from(diff, shots, frames, share={"full": 0.6})   # cards and titles cover part of the plate
    plan = M.plan(frames=frames, cuts=cuts, shots=shots, words=proj.words_raw, accents=(), graphic_events=g_events,
                  cfg=cfg, alive=alive, strong_events=strong)
    script, grain = M.ensure_assets(proj.dir, cfg)
    js = M.emit_js(plan, words=proj.words_raw) + M.grain_js(cfg, frames)
    plain = [[a, b] for a, b, lv in plan["levels"] if M.for_level(cfg, lv).get("captions") != "kinetic"]
    if any(M.for_level(cfg, lv).get("captions") == "kinetic" for _a, _b, lv in plan["levels"]):
        js.append("var RRM_PLAIN = " + json.dumps(plain) + ";")   # beats whose own level keeps captions plain
        js.append(CAPTION_JS)
    vig = '<div id="mvVig"></div>' if cfg.get("vignette") and 'id="aroll"' in m.group(1) else ""   # base.mp4 bakes its own
    # a template may hand layers that ride the camera with the speaker (a page and a live cut-out): a
    # <!--mvcam-->...<!--/mvcam--> block right after the video. The video then gets its own wrapper div (the renderer
    # stacks a video's frames next to it, so it must be alone in its parent).
    end, vid = m.end(), m.group(1)
    xm = re.match(r"\s*<!--mvcam-->(.*?)<!--/mvcam-->", body[end:], re.S)
    if xm:
        vid = '<div class="mv-vid">' + vid + "</div>" + xm.group(1)
        end += xm.end()
    wrapped = (M.DEFS_HTML + '<div id="mvT" data-layout-allow-overflow><div id="mvCam" data-layout-allow-overflow>'
               + vid + '</div>' + vig + '</div>' + M.top_layers_html(cfg, grain))
    plan["cuts"] = [{k: v for k, v in c.items() if k != "override"} for c in cuts]
    plan["shots"] = [{k: v for k, v in x.items() if k != "override"} for x in shots]
    plan["graphic_events"] = [{"t": round(e["frame"] / FPS, 3), "kind": e["kind"], "what": e.get("label", "")} for e in ev]
    M.write_plan(proj.dir, plan)
    ink = proj.colors.get("ink", "#0C0C0F")
    css_ = M.css(cfg, ink, z="auto") + "#mvIris,#mvFlash{z-index:auto}\n"   # cards and captions stay above the iris
    return {"body": body[:m.start()] + wrapped + body[end:], "css": css_, "js": js,
            "script": script, "plan": plan}


def ensure_gsap(project_dir):
    dest = os.path.join(project_dir, "assets", "gsap.min.js")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cache = os.path.join(theme.HOME, "cache", f"gsap-{GSAP_VER}.min.js")
    if not os.path.exists(cache):
        import urllib.request
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        urllib.request.urlretrieve(GSAP_CDN, cache)
    shutil.copyfile(cache, dest)
    return "assets/gsap.min.js"


def fontface(proj, warn=print, italic=()):
    return theme.resolve_fonts(proj.brand, proj.dir, warn, italic=tuple(italic))


def fam(name):
    return theme.fam(name)


def rgba(hex_, a):
    return theme.rgba(hex_, a)


def write_hf_config(project_dir):
    cfg = os.path.join(project_dir, "hyperframes.json")
    if not os.path.exists(cfg):
        jsave(cfg, {"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                    "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}}, 2)


# ----------------------------------------------------------------------------- chrome sampling + stills
def sample(index_html, frames, step=3, timeout=240, exact=None):
    """Every `step`-th frame (or the `exact` frame list): every visible [data-box] element's on-screen rect
    (transforms included); with `exact`, also the visibility of every element with an id."""
    chrome = _measure.find_chrome()
    if not chrome:
        raise SystemExit("no headless Chrome found (run: npx --yes hyperframes@0.8.34 doctor)")
    mode = ("frames:" + ",".join(map(str, exact))) if exact else f"sample:{step}:{frames}"
    url = Path(os.path.abspath(index_html)).as_uri() + "#" + mode
    cmd = [chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
           "--window-size=1080,1920", "--virtual-time-budget=20000", "--dump-dom", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    m = re.search(r'<pre id="rr-out">(.*?)</pre>', r.stdout, re.S)
    if not m:
        raise SystemExit("timeline sampling failed (page error?) " + r.stderr[-400:])
    return json.loads(_html.unescape(m.group(1)))


def still(index_html, frame, png_path):
    """Screenshot of the composition's graphics at `frame` (video layers are not decoded here: use for cutaways)."""
    chrome = _measure.find_chrome()
    run([chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
         f"--window-size={W},{H}", "--virtual-time-budget=6000", f"--screenshot={png_path}",
         Path(os.path.abspath(index_html)).as_uri() + f"#seek:{frame}"], timeout=90)
    return png_path


def screenshot_html(html_path, png_path, w=W, h=H):
    """Transparent PNG of a static HTML page (used for text layers composited behind the speaker)."""
    chrome = _measure.find_chrome()
    run([chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
         f"--window-size={w},{h}", "--default-background-color=00000000", "--virtual-time-budget=4000",
         f"--screenshot={png_path}", Path(os.path.abspath(html_path)).as_uri()], timeout=90)
    return png_path


# ----------------------------------------------------------------------------- lint + render
HF = ["npx", "--yes", "hyperframes@0.8.34"] if os.name != "nt" else ["npx.cmd", "--yes", "hyperframes@0.8.34"]


def lint(project_dir):
    import render as _r  # split template render.py (lint parser)
    errs, warns, out = _r.lint(project_dir)
    return errs, warns, _r.short_findings(out)


def render(project_dir, rel_out, quality="high"):
    import render as _r
    dt, _ = _r.render_to(project_dir, rel_out, quality)
    return dt


# ----------------------------------------------------------------------------- audio
SR = 48000


def read_audio(path, frames=None, pad_to_frames=None):
    """Float32 stereo (n,2) at 48 kHz from any media file; trimmed/padded to frames/30 s when given."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    n = pad_to_frames or frames
    if n:
        want = int(round(n * SR / FPS))
        if len(a) < want:
            a = np.vstack([a, np.zeros((want - len(a), 2), np.float32)])
        a = a[:want]
    return a


def write_wav(path, a):
    import numpy as np
    pcm = np.clip(a, -1, 1).astype(np.float32).tobytes()
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-c:a", "pcm_s24le", path], input=pcm, capture_output=True)
    if p.returncode:
        raise SystemExit(p.stderr.decode()[-500:])


def ebur128(path):
    """(integrated LUFS, max momentary LUFS, true peak dBTP) of a file."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                        "ebur128=peak=true:metadata=1,ametadata=mode=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    ms = [float(x) for x in re.findall(r"lavfi\.r128\.M=(-?[\d.]+)", r.stdout) if x not in ("-inf",)]
    summ = r.stderr[r.stderr.rfind("Summary:"):]
    mi = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summ)
    mp = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summ)
    f = lambda v: float("-inf") if v in (None, "-inf") else float(v)  # noqa: E731
    return f(mi.group(1) if mi else None), (max(ms) if ms else float("-inf")), f(mp.group(1) if mp else None)


def mix_and_master(project_dir, render_path, voice_src, cues, out_path, frames, margin_db=20.0, voice_offset_frames=0,
                   vbitrate="9500k", motion_sfx=True, preset="slow"):
    """Voice (untouched, from voice_src) + synthesized SFX cues -> muxed with the render's video -> -14 LUFS master.
    Each cue is scaled so its loudest 400 ms sits `margin_db` LU under the voice's integrated loudness.
    Returns a report with the measured margin for every cue."""
    import numpy as np
    import sfx as _sfx
    from deliver import make_master  # engine/deliver.py
    work = tempfile.mkdtemp(prefix="mix_", dir=project_dir)
    try:
        voice = read_audio(voice_src)
        if voice_offset_frames:
            voice = voice[int(round(voice_offset_frames * SR / FPS)):]
        want = int(round(frames * SR / FPS))
        voice = np.vstack([voice, np.zeros((max(0, want - len(voice)), 2), np.float32)])[:want]
        # 15 ms fade at the very end so a padded tail never clicks
        fade = int(0.015 * SR)
        voice[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
        vwav = os.path.join(work, "voice.wav")
        write_wav(vwav, voice)
        v_i, v_m, v_tp = ebur128(vwav)
        fx = np.zeros_like(voice)
        level_cache, rep = {}, []
        for c in cues:
            snd = _sfx.make(c["name"])
            if c["name"] not in level_cache:
                tmp = os.path.join(work, f"cue_{c['name']}.wav")
                write_wav(tmp, np.vstack([np.zeros((SR // 2, 2), np.float32), snd, np.zeros((SR // 2, 2), np.float32)]))
                level_cache[c["name"]] = ebur128(tmp)[1]
            target = v_i - margin_db + c.get("gain_db", 0.0)
            g = 10 ** ((target - level_cache[c["name"]]) / 20)
            s0 = int(round(c["frame"] * SR / FPS)) + int(_sfx.LEAD.get(c["name"], 0) * SR)
            s0 = max(0, s0)
            seg = snd[: max(0, len(fx) - s0)] * g
            fx[s0:s0 + len(seg)] += seg
            rep.append({**c, "level_lufs_m": round(target, 1)})
        fwav = os.path.join(work, "sfx.wav")
        write_wav(fwav, fx)
        f_i, f_m, f_tp = ebur128(fwav) if cues else (float("-inf"),) * 3
        if cues and v_i - f_m < margin_db - 0.5:  # cues stacked inside one 400 ms window: pull the whole bus down
            fx *= 10 ** (-(margin_db - (v_i - f_m)) / 20)
            write_wav(fwav, fx)
            f_i, f_m, f_tp = ebur128(fwav)
        if motion_sfx:
            mbus, mrep = motion_bus(project_dir, voice, len(voice), v_i)
        else:   # the voice-only deliverable
            mbus, mrep = np.zeros_like(voice), {"mode": "off", "placed": []}
        mix = voice + fx + mbus
        mwav = os.path.join(work, "mix.wav")
        write_wav(mwav, mix)
        muxed = os.path.join(work, "muxed.mp4")
        # video re-encoded once here (about 9.5 Mbps: a 35 s demo lands near 42 MB), audio mixed; master copies video
        run(["ffmpeg", "-v", "error", "-y", "-i", render_path, "-i", mwav, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", preset, "-b:v", vbitrate, "-maxrate", "12M", "-bufsize", "18M",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "320k", "-shortest", muxed])
        m = make_master(muxed, out_path)
        report = {"voice_lufs": round(v_i, 2), "voice_true_peak": round(v_tp, 2), "sfx_max_momentary": round(f_m, 2),
                  "motion_sfx": {"mode": mrep.get("mode"), "placed": len(mrep.get("placed", [])),
                                 "under_voice_db": mrep.get("under_voice_db")},
                  "sfx_margin_lu": (round(v_i - f_m, 2) if cues else None), "cues": rep, "master": m}
        os.makedirs(os.path.join(project_dir, "work"), exist_ok=True)
        shutil.copyfile(vwav, os.path.join(project_dir, "work", "voice_stem.wav"))
        shutil.copyfile(fwav, os.path.join(project_dir, "work", "sfx_stem.wav"))
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def motion_bus(project_dir, voice, n, v_lufs):
    """Motion v2 SFX on the motion plan's transitions (the template's own cues already cover its graphics)."""
    import numpy as np
    import mixer
    plan = M.load_plan(project_dir)
    pj = jload(os.path.join(project_dir, "project.json"), {})
    if not plan or pj.get("motion") is False:
        return np.zeros((n, 2), np.float32), {"mode": "off", "placed": []}
    mode = M.config(pj)["sfx"]
    bus, rep = mixer.build_bus(plan.get("events", []), n, v_lufs, mode, include_inserts=False,
                               stem_path=os.path.join(project_dir, "work", "motion_sfx_stem.wav"))
    mixer.write_report(project_dir, rep)
    return bus, rep


# ----------------------------------------------------------------------------- deliverables
def make_loop(master, out, t0, dur=6.0, cap_mb=4.0):
    for crf in (20, 23, 26, 29, 32):
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", master, "-t", f"{dur:.3f}", "-an", "-c:v", "libx264",
             "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
        if os.path.getsize(out) < cap_mb * 1e6:
            return {"crf": crf, "mb": round(os.path.getsize(out) / 1e6, 2)}
    raise SystemExit(f"loop over {cap_mb} MB even at crf 32")


def make_poster(master, out, t):
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", master, "-frames:v", "1", "-q:v", "2", out])


def grab(video, frames, scale=360):
    """Exact frames (by index) as small RGB numpy arrays."""
    import numpy as np
    h = int(scale * 16 / 9)
    want, out = sorted(set(frames)), {}
    for i in range(0, len(want), 80):          # ffmpeg's expression parser fails past ~100 terms: batch it
        part = want[i:i + 80]
        sel = "+".join(f"eq(n\\,{f})" for f in part)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"select='{sel}',scale={scale}:{h}",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        out.update(zip(part, np.frombuffer(raw, np.uint8).reshape(-1, h, scale, 3)))
    return out


def label_sheet(images, labels, out, cols=6):
    from PIL import Image, ImageDraw
    if not images:
        return
    h, w = images[0].shape[:2]
    rows = math.ceil(len(images) / cols)
    sheet = Image.new("RGB", (cols * w, rows * (h + 26)), (18, 18, 20))
    d = ImageDraw.Draw(sheet)
    for i, (im, lb) in enumerate(zip(images, labels)):
        x, y = (i % cols) * w, (i // cols) * (h + 26)
        sheet.paste(Image.fromarray(im), (x, y + 26))
        d.text((x + 6, y + 6), lb[:48], fill=(240, 240, 240))
    sheet.save(out, quality=88)
