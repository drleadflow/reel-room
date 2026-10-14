#!/usr/bin/env python3
"""Text collision check on a HyperFrames composition (the same index.html the renderer draws).

  python textcheck.py <project> [--index index.html] [--frames N] [--step 3] [--persist 8] [--out FILE] [--json]

Loads the page once in headless Chrome (--dump-dom with a virtual time budget, no node, no puppeteer), waits for
window.__timelines.main and the fonts, then seeks the timeline every `step` frames and measures every visible text
element per character (line boxes, word gaps, clip panels). Python then judges the samples:
  overlap      two different text elements' line boxes intersect by more than 6% of the smaller box
  wrap         a headline (not a caption) wraps onto more than one line
  orphan       a multi-line block of 4+ words whose last line is a single word
  overflow     a text line past the frame edge
  clip         a text line past the panel that clips it (overflow hidden or clip-path inset)
  gap          a gap between two words on one line under 0.18em
  tracking     letter-spacing tighter than -0.03em            (counts on any sample)
  wordspacing  word-spacing below zero                         (counts on any sample)
  doublecap    more than one caption visible at once           (counts on any sample)
Every other finding only counts when it holds on >= `persist` consecutive samples (entrances and transitions pass
through transient states).

Frame count: --frames, else layout_boxes.json `frames`, else sum(frames) in segments.json, else work/meta.json.
The instrumented page goes to a temp folder (with <base href> back to the project); the only file written in the
project is the report, <project>/qa/textcheck.json (or --out).
Exit code 0 = pass, 1 = fail, 2 = could not run.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SPLIT_DIR = Path(__file__).resolve().parent.parent / "templates" / "split"

OVERLAP_FRAC = 0.06
GAP_EM = 0.18
TRACKING_EM = -0.0305          # "tighter than -0.03em" with a rounding margin, as in the original mjs
CLIP_PAD = 2
LINE_ROW_FRAC = 0.45
HARD_KINDS = {"tracking", "wordspacing", "doublecap"}
DEFAULT_CANVAS = (1080, 1920)
POLL_MS, POLL_MAX = 250, 240   # wait up to 60 s (virtual) for window.__timelines.main
LABEL = "No text overlaps, overflows or cramped words"
PLAIN = {"overlap": "text overlaps other text", "wrap": "headline wraps", "orphan": "one-word last line",
         "overflow": "text past the frame edge", "clip": "text cut off by its panel", "gap": "cramped word gap",
         "tracking": "letter-spacing too tight", "wordspacing": "word-spacing tightened",
         "doublecap": "two captions on screen at once"}


class TextcheckError(Exception):
    """Could not run. skip=True means the project simply has nothing to check here (no page, no browser)."""

    def __init__(self, msg, fix="", skip=False):
        super().__init__(msg)
        self.fix, self.skip = fix, skip


# ----------------------------------------------------------------------------- page instrumentation (JS)
SAMPLE_JS = r"""
function sample(t) {
  const tl = window.__timelines.main; tl.seek(t, false);
  const root = document.getElementById("root") || document.body, o = root.getBoundingClientRect();
  const vis = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) < 0.35) return false; } return true; };
  const clipOf = (el) => { for (let e = el.parentElement; e && e !== root; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.overflow === "hidden" || (cs.clipPath && cs.clipPath !== "none")) { const r = e.getBoundingClientRect();
        if (r.width > 40 && r.height > 40) return [r.left - o.left, r.top - o.top, r.right - o.left, r.bottom - o.top, e.id || String(e.className || "")]; } } return null; };
  const owners = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.textContent.trim()) continue;
    const p = n.parentElement; if (!p || p.closest("script,style,pre,svg")) continue;
    let own = p.closest("[data-box]");
    const blockUp = (e) => { while (e && e !== root) { const d = getComputedStyle(e).display; if (d !== "inline" && d !== "inline-block" && d !== "contents") return e; e = e.parentElement; } return p; };
    if (!own || [...own.querySelectorAll("*")].some((k) => k.textContent.trim() && ["block", "flex", "grid"].includes(getComputedStyle(k).display))) own = blockUp(p);
    owners.add(own);
  }
  const ownerOf = new Map();
  for (const el of owners) { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) {
    const cur = ownerOf.get(n); if (!cur || cur.contains(el)) ownerOf.set(n, el); } }
  const clipRect = (e) => { const st = getComputedStyle(e); const r = e.getBoundingClientRect();
    if (st.overflow === "hidden") return r;
    const m = /inset\(([^)]*)\)/.exec(st.clipPath || ""); if (!m) return null;
    const v = m[1].replace(/round.*/, "").trim().split(/\s+/).map((x, i) => x.endsWith("%") ? parseFloat(x) / 100 * ((i % 2) ? r.width : r.height) : parseFloat(x));
    const [t, rr, bb, l] = [v[0], v[1] ?? v[0], v[2] ?? v[0], v[3] ?? v[1] ?? v[0]];
    return { left: r.left + l, right: r.right - rr, top: r.top + t, bottom: r.bottom - bb }; };
  const out = [];
  for (const el of owners) {
    if (!vis(el)) continue;
    const txt = el.textContent.replace(/\s+/g, " ").trim(); if (!txt) continue;
    const cs = getComputedStyle(el); const fsz = parseFloat(cs.fontSize);
    let tilt = 0;   // summed rotation (rad) of the element and its ancestors: rotate property + transform matrices
    for (let e = el; e && e !== root; e = e.parentElement) { const st = getComputedStyle(e);
      if (st.rotate && st.rotate !== "none") tilt += parseFloat(st.rotate) * Math.PI / 180;
      const mm = /matrix(?:3d)?\(([^)]*)\)/.exec(st.transform || ""); if (mm) { const v = mm[1].split(",").map(parseFloat); tilt += Math.atan2(v[1], v[0]); } }
    if (Math.abs(tilt) > 20 * Math.PI / 180) continue;
    const sinT = Math.abs(Math.sin(tilt)), cosT = Math.cos(tilt);
    const chars = [];
    const w2 = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = w2.nextNode(); n; n = w2.nextNode()) {
      if (ownerOf.get(n) !== el) continue;
      const pe = n.parentElement; if (!vis(pe)) continue;
      const pcs = getComputedStyle(pe), pr = pe.getBoundingClientRect();
      const psc = pe.offsetWidth > 0 && pr.width > 0 ? pr.width / pe.offsetWidth : 1;   // on-screen scale (a card scaled by a transform)
      const pfs = parseFloat(pcs.fontSize) * psc;                                       // so gaps are judged in on-screen ems
      const cv = (window.__tcv = window.__tcv || document.createElement("canvas").getContext("2d")); cv.font = `${pcs.fontStyle} ${pcs.fontWeight} ${pcs.fontSize} ${pcs.fontFamily}`;
      const mt = cv.measureText(n.textContent.trim() || "x"); const asc = mt.actualBoundingBoxAscent, dsc = mt.actualBoundingBoxDescent, fasc = mt.fontBoundingBoxAscent;
      const clips = []; for (let e = pe; e && e !== root; e = e.parentElement) { const cr = clipRect(e); if (cr) clips.push(cr); }
      for (let i = 0; i < n.length; i++) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
        const b = r.getBoundingClientRect(); const c = n.textContent[i];
        if (b.width === 0 && c !== " ") continue;
        const mx = (b.left + b.right) / 2, my = (b.top + b.bottom) / 2;
        if (clips.some((q) => mx < q.left || mx > q.right || my < q.top || my > q.bottom)) continue;
        const k = b.height / Math.max(1, (mt.fontBoundingBoxAscent + mt.fontBoundingBoxDescent));
        const base = b.top + fasc * k;
        chars.push({ c, rh: b.height, x0: b.left - o.left, x1: b.right - o.left, y0: base - asc * k - o.top, y1: base + dsc * k - o.top, fs: pfs }); }
    }
    const ink = chars.filter((c) => c.c.trim());
    if (!ink.length) continue;
    const lines = [];
    for (const c of ink) { const cy = (c.y0 + c.y1) / 2; let L = lines.find((l) => Math.abs(l.cy - cy) < c.fs * __ROW__);
      if (!L) { L = { cy, x0: c.x0, x1: c.x1, y0: c.y0, y1: c.y1 }; lines.push(L); }
      L.x0 = Math.min(L.x0, c.x0); L.x1 = Math.max(L.x1, c.x1); L.y0 = Math.min(L.y0, c.y0); L.y1 = Math.max(L.y1, c.y1); c.L = L; }
    const gaps = [];
    for (let i = 1; i < chars.length - 1; i++) {
      if (chars[i].c !== " ") continue;
      let a = i - 1, b = i + 1; while (b < chars.length && chars[b].c === " ") b++;
      if (b >= chars.length || !chars[a].c.trim() || !chars[b].c.trim()) continue;
      if (Math.abs((chars[a].y0 + chars[a].y1) / 2 - (chars[b].y0 + chars[b].y1) / 2) > chars[a].fs * __ROW__) continue;
      // a tilted line: neighbouring glyph boxes overlap by about H*sin(tilt) in x, so undo that before judging
      const g = (chars[b].x0 - chars[a].x1 + Math.min(chars[a].rh, chars[b].rh) * cosT * sinT) / cosT;
      gaps.push(+(g / chars[a].fs).toFixed(3));
    }
    const last = lines.reduce((p, q) => (q.cy > p.cy ? q : p), lines[0]);
    let llw = 0, prevInk = null;
    for (const c of chars) { const isInk = !!c.c.trim(); if (isInk && c.L === last && (!prevInk || prevInk.L !== last)) llw++; prevInk = isInk ? c : null; }
    const words = txt.split(" ");
    const ls = cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing) / fsz;
    out.push({ id: el.id || "", cls: (el.className && el.className.baseVal === undefined ? el.className : "") + "", text: txt.slice(0, 60),
      cap: !!el.closest(".cap"), lines: lines.map((l) => [l.x0, l.y0, l.x1, l.y1].map((v) => Math.round(v))), nlines: lines.length,
      words: words.length, last_len: words[words.length - 1].length, last_line_words: lines.length > 1 ? llw : 0,
      ls: +ls.toFixed(3), ws: cs.wordSpacing, gaps, clip: clipOf(el), fs: fsz });
  }
  return out;
}
"""

DRIVER_JS = r"""
(function () {
  var FRAMES = __FRAMES__, FPS = __FPS__, errs = [];
  window.__timelines = window.__timelines || {};
  window.addEventListener("error", function (e) { errs.push(String(e.message || e)); });
  function done(obj) { obj.errors = errs; var pre = document.createElement("pre"); pre.id = "tcOut";
    pre.textContent = JSON.stringify(obj); document.body.appendChild(pre); }
  function go() {
    var tl = window.__timelines.main, res = [], i = 0;
    try { if (tl.pause) tl.pause(); } catch (e) {}
    var r = (document.getElementById("root") || document.body).getBoundingClientRect();
    (function next() {
      var end = Math.min(FRAMES.length, i + 8);
      try { for (; i < end; i++) res.push({ f: FRAMES[i], els: sample((FRAMES[i] + 0.5) / FPS) }); }
      catch (e) { return done({ error: "sampling failed at frame " + FRAMES[i] + ": " + e.message }); }
      if (i < FRAMES.length) setTimeout(next, 0); else done({ canvas: [Math.round(r.width), Math.round(r.height)], samples: res });
    })();
  }
  function ready() {
    var fs = document.fonts, all = fs ? Promise.all(Array.from(fs).map(function (f) { return f.load().catch(function () {}); }))
      .then(function () { return fs.ready; }) : Promise.resolve();
    all.then(function () { setTimeout(go, 500); }, function () { setTimeout(go, 500); });
  }
  function wait(n) {
    if (window.__timelines && window.__timelines.main && window.__timelines.main.seek) return ready();
    if (n >= __POLLMAX__) return done({ error: "timeline never registered (window.__timelines.main)" });
    setTimeout(function () { wait(n + 1); }, __POLLMS__);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { wait(0); });
  else wait(0);
})();
"""


def instrument(src, project_dir, frames_list, fps=C.FPS):
    """Return the page source with <base href> to the project and the sampling script before </body>."""
    base = '<base href="' + Path(project_dir).resolve().as_uri().rstrip("/") + '/">'
    m = re.search(r"<head[^>]*>", src, re.I)
    src = (src[:m.end()] + base + src[m.end():]) if m else base + src
    js = (SAMPLE_JS.replace("__ROW__", str(LINE_ROW_FRAC)) + DRIVER_JS
          .replace("__FRAMES__", json.dumps(frames_list)).replace("__FPS__", str(fps))
          .replace("__POLLMAX__", str(POLL_MAX)).replace("__POLLMS__", str(POLL_MS)))
    tag = "<script>" + js + "</script>"
    i = src.lower().rfind("</body>")
    return src[:i] + tag + src[i:] if i >= 0 else src + tag


# ----------------------------------------------------------------------------- inputs
def frame_count(project, frames=None):
    """--frames, else layout_boxes.json frames, else sum(frames) in segments.json, else work/meta.json frames."""
    if frames:
        return int(frames)
    p = Path(project)
    lb = C.read_json(p / "layout_boxes.json", {}) if (p / "layout_boxes.json").exists() else {}
    if isinstance(lb, dict) and lb.get("frames"):
        return int(lb["frames"])
    segs = C.read_json(p / "segments.json", []) if (p / "segments.json").exists() else []
    segs = segs.get("segments", []) if isinstance(segs, dict) else segs
    total = sum(int(s.get("frames", 0)) for s in segs if isinstance(s, dict))
    if total:
        return total
    meta = C.read_json(p / "work" / "meta.json", {}) if (p / "work" / "meta.json").exists() else {}
    return int(meta["frames"]) if isinstance(meta, dict) and meta.get("frames") else None


def canvas_size(src, measured=None):
    """Frame size: the root's data-width/data-height, else the measured root box (when non-empty), else 1080x1920."""
    m = re.search(r'id="root"[^>]*>', src)
    tag = m.group(0) if m else ""
    w, h = re.search(r'data-width="(\d+)"', tag), re.search(r'data-height="(\d+)"', tag)
    if w and h:
        return int(w.group(1)), int(h.group(1))
    if measured and len(measured) == 2 and min(measured) > 0:
        return int(measured[0]), int(measured[1])
    return DEFAULT_CANVAS


def find_chrome():
    """templates/split/measure.py find_chrome() (loaded by path so no other `measure` module can shadow it)."""
    try:
        spec = importlib.util.spec_from_file_location("reel_split_measure", SPLIT_DIR / "measure.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.find_chrome()
    except (OSError, ImportError, AttributeError) as e:
        print(f"textcheck: could not load measure.find_chrome ({e}); falling back to PATH", file=sys.stderr)
        return shutil.which("google-chrome") or shutil.which("chromium")


# ----------------------------------------------------------------------------- browser run
def chrome_cmd(chrome, url, canvas, budget_ms):
    cmd = [chrome]
    if "headless-shell" not in os.path.basename(chrome):
        cmd.append("--headless=new")
    return cmd + ["--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
                  "--mute-audio", "--force-device-scale-factor=1", f"--window-size={canvas[0]},{canvas[1]}",
                  f"--virtual-time-budget={budget_ms}", "--dump-dom", url]


def parse_dump(stdout):
    """Pull the JSON the page left in <pre id="tcOut">."""
    m = re.search(r'<pre id="tcOut">(.*?)</pre>', stdout or "", re.S)
    if not m:
        raise TextcheckError("the page never produced measurements (no <pre id=\"tcOut\"> in the dumped DOM)",
                             "Open index.html in a browser and check the console; the timeline or a script may be failing.")
    try:
        return json.loads(html.unescape(m.group(1)))
    except json.JSONDecodeError as e:
        raise TextcheckError(f"measurement output was not valid JSON ({e})") from e


def sample_page(page_src, project_dir, frames_list, canvas):
    chrome = find_chrome()
    if not chrome:
        raise TextcheckError("no Chrome found", "Install Chrome or run `npx hyperframes doctor`, or set REEL_ROOM_CHROME.",
                             skip=True)
    n = len(frames_list)
    budget = POLL_MAX * POLL_MS + 15000 + n * 40
    timeout = 120 + n * 3
    tmp = tempfile.mkdtemp(prefix="textcheck_")
    try:
        page = Path(tmp) / "textcheck.html"
        page.write_text(instrument(page_src, project_dir, frames_list), encoding="utf-8")
        try:
            r = subprocess.run(chrome_cmd(chrome, page.as_uri(), canvas, budget), capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise TextcheckError(f"Chrome did not finish in {timeout} s", "Raise --step to sample fewer frames.") from e
        except OSError as e:
            raise TextcheckError(f"could not start Chrome ({e})", "Check the Chrome install (npx hyperframes doctor).") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    data = parse_dump(r.stdout)
    if data.get("error"):
        raise TextcheckError(data["error"] + _errs(data), "Check that index.html registers window.__timelines.main.")
    return data


def _errs(data):
    e = data.get("errors") or []
    return f" (page errors: {'; '.join(e[:3])})" if e else ""


# ----------------------------------------------------------------------------- judging (pure)
def _num(v):
    m = re.match(r"\s*(-?\d+(\.\d+)?)", str(v))
    return float(m.group(1)) if m else None


def element_notes(e, canvas=DEFAULT_CANVAS):
    """[(kind, what, msg)] for one measured element in one sample."""
    tag = f"{e.get('id') or e.get('cls', '')}:{e.get('text', '')}"
    notes = []
    if e.get("ls", 0) < TRACKING_EM and len(e.get("text", "")) > 1:
        notes.append(("tracking", tag, f"letter-spacing {e['ls']}em"))
    ws = _num(e.get("ws"))
    if ws is not None and ws < 0:
        notes.append(("wordspacing", tag, f"word-spacing {e['ws']} (tightened)"))
    notes += [("gap", tag, f"word gap {g}em") for g in e.get("gaps", []) if g < GAP_EM]
    if e.get("nlines", 1) > 1 and not e.get("cap") and e.get("words", 1) > 1:
        notes.append(("wrap", tag, f"wraps onto {e['nlines']} lines"))
    if e.get("nlines", 1) > 1 and e.get("words", 1) > 3 and e.get("last_line_words") == 1 and e.get("last_len", 2) > 1:
        notes.append(("orphan", tag, "last line is a single word"))
    notes += line_notes(e, tag, canvas)
    return notes


def line_notes(e, tag, canvas=DEFAULT_CANVAS):
    notes, c = [], e.get("clip")
    for ln in e.get("lines", []):
        if ln[0] < 0 or ln[2] > canvas[0] or ln[1] < 0 or ln[3] > canvas[1]:
            notes.append(("overflow", tag, f"line {ln} past the frame"))
        if c and (ln[0] < c[0] - CLIP_PAD or ln[2] > c[2] + CLIP_PAD or ln[1] < c[1] - CLIP_PAD or ln[3] > c[3] + CLIP_PAD):
            notes.append(("clip", tag, f"line {ln} past panel {c[4]} {[round(v) for v in c[:4]]}"))
    return notes


def overlap_frac(a, b):
    """Intersection area over the smaller of the two boxes [x0,y0,x1,y1]; 0 when they do not touch."""
    ix, iy = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / area if area > 0 else 0.0


def overlap_notes(els):
    notes = []
    for i, A in enumerate(els):
        for B in els[i + 1:]:
            best = max((overlap_frac(a, b) for a in A.get("lines", []) for b in B.get("lines", [])), default=0.0)
            if best > OVERLAP_FRAC:
                what = f"{A.get('id') or A.get('cls', '')}:{A.get('text', '')}|{B.get('id') or B.get('cls', '')}:{B.get('text', '')}"
                notes.append(("overlap", what, f"{round(100 * best)}%"))
    return notes


def sample_notes(els, canvas=DEFAULT_CANVAS):
    """All findings for one sample: per element, pairwise overlaps, and two captions at once."""
    notes = [n for e in els for n in element_notes(e, canvas)] + overlap_notes(els)
    caps = [e.get("text", "") for e in els if e.get("cap")]
    if len(caps) > 1:
        notes.append(("doublecap", " | ".join(caps), f"{len(caps)} captions visible"))
    return notes


def collect(samples, canvas=DEFAULT_CANVAS):
    """{(kind, what): [(frame, msg)]}, one entry per frame (several gaps in one element count once per sample)."""
    seen = {}
    for s in samples:
        for kind, what, msg in sample_notes(s.get("els", []), canvas):
            hits = seen.setdefault((kind, what), [])
            if not hits or hits[-1][0] != s["f"]:
                hits.append((s["f"], msg))
    return seen


def longest_run(frames, step):
    """(length, first frame) of the longest run of samples exactly `step` frames apart."""
    best, at, run = 1, frames[0], 1
    for i in range(1, len(frames)):
        run = run + 1 if frames[i] - frames[i - 1] == step else 1
        if run > best:
            best, at = run, frames[i - run + 1]
    return best, at


def persist_filter(seen, step, persist):
    """Keep findings that hold on >= persist consecutive samples; HARD_KINDS count on any sample."""
    fails = {}
    for (kind, what), hits in seen.items():
        best, at = longest_run([f for f, _ in hits], step)
        if best >= persist or kind in HARD_KINDS:
            msg = next(m for f, m in hits if f == at)
            fails.setdefault(kind, []).append({"what": what, "first_frame": at, "samples": best, "msg": msg})
    return fails


def judge(samples, step, persist, canvas=DEFAULT_CANVAS):
    return persist_filter(collect(samples, canvas), step, persist)


def describe(fails, limit=3):
    """Plain words, first `limit` findings (earliest frame first) with frame numbers."""
    items = sorted(((x["first_frame"], k, x) for k, v in fails.items() for x in v), key=lambda t: (t[0], t[1]))
    n = len(items)
    if not n:
        return "no text problems found"
    parts = [f"{PLAIN.get(k, k)} at frame {f}: {x['what'][:70]} ({x['msg']})" for f, k, x in items[:limit]]
    return f"{n} text problem{'s' if n != 1 else ''}: " + "; ".join(parts) + ("; ..." if n > limit else "")


# ----------------------------------------------------------------------------- run / check / cli
def run(project, index="index.html", frames=None, step=3, persist=8, out=None):
    """Sample the page, judge it, write the report (default <project>/qa/textcheck.json). Raises TextcheckError."""
    proj = Path(project).expanduser().resolve()
    page = proj / index
    if not page.is_file():
        raise TextcheckError(f"no {index} in {proj}", "Build the composition first (it writes index.html).", skip=True)
    n = frame_count(proj, frames)
    if not n:
        raise TextcheckError("frame count unknown", "Pass --frames N (or write layout_boxes.json / segments.json).",
                             skip=True)
    step = max(1, int(step))
    src = page.read_text(encoding="utf-8", errors="replace")
    t0 = time.time()
    data = sample_page(src, proj, list(range(0, n, step)), canvas_size(src))
    canvas = canvas_size(src, data.get("canvas"))
    fails = judge(data.get("samples", []), step, persist, canvas)
    report = {"project": str(proj), "index": index, "step": step, "persist": persist, "frames": n,
              "samples": len(data.get("samples", [])), "seconds": round(time.time() - t0, 1),
              "page_errors": data.get("errors", [])[:10], "pass": not fails, "fails": fails}
    C.write_json(out or proj / "qa" / "textcheck.json", report)
    return report


def check(project, index="index.html", frames=None, step=3, persist=8, out=None):
    """qa.py check shape {name, pass, detail, label[, skipped]}."""
    base = {"name": "text_collision", "label": LABEL}
    try:
        rep = run(project, index=index, frames=frames, step=step, persist=persist, out=out)
    except TextcheckError as e:
        if e.skip:
            return {**base, "pass": True, "skipped": True, "detail": f"skipped: {e}"}
        return {**base, "pass": False, "detail": f"could not measure text: {e}"}
    return {**base, "pass": rep["pass"], "detail": describe(rep["fails"]) + f" ({rep['samples']} samples, step {step})"}


def main():
    ap = argparse.ArgumentParser(description="Text collision check on a HyperFrames composition.")
    ap.add_argument("project")
    ap.add_argument("--index", default="index.html")
    ap.add_argument("--frames", type=int)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--persist", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = C.Out(a.json)
    try:
        rep = run(a.project, a.index, a.frames, a.step, a.persist, a.out)
    except TextcheckError as e:
        C.fail(str(e), e.fix, a.json)
    out.log(f"TEXTCHECK {'PASS' if rep['pass'] else 'FAIL'}: {rep['samples']} samples in {rep['seconds']} s")
    for kind, items in rep["fails"].items():
        out.log(f"  {kind}: {len(items)}")
        for x in items[:12]:
            out.log(f"    f{x['first_frame']} x{x['samples']}  {x['what'][:90]}  ({x['msg']})")
    out.result(rep)
    sys.exit(0 if rep["pass"] else 1)


if __name__ == "__main__":
    main()
