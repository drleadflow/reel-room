#!/usr/bin/env python3
"""Reel Room colour grade: measure the footage, offer three safe looks, preview them, apply one.

  python grade.py <project> analyze [--json]
  python grade.py <project> preview [--t SECONDS] [--json]
  python grade.py <project> apply <clean|warm|dark|none> [--json]

analyze   Takes 5 frames from assets/aroll.mp4 (10/30/50/70/90 %), measures mean luma + clipping, white balance
          (gray world, with the face and strongly coloured pixels left out so a coloured wall does not fool it)
          and skin hue inside the face box (work/facepos.json, else an OpenCV face finder). It then builds three
          ffmpeg filter chains and writes work/grade.json:
            clean  correction only: exposure to a healthy skin brightness, small white-balance fix on the
                   warm/cool axis, highlight roll-off if whites clip. Nothing stylistic.
            warm   clean + editorial warmth: golden (yellow, not red) mids and highlights, a touch more colour.
            dark   clean + contrast punch: deeper shadows, S-curve, slightly lower gamma, faces kept lit.
          Each option has a one-line plain-English reason.
          Hard rules, enforced by measuring the graded frames and backing the strength off until they hold:
            - no film grain, no noise/blur filters in any chain
            - skin hue never moves toward red or magenta (median skin hue shift >= -1.0 OpenCV units, and not
              pushed more than +6 toward yellow), skin saturation does not jump
            - highlights do not clip more than the source does (+0.2 % tolerance), shadows are not crushed
              beyond a tolerance, face stays in a sane brightness range
preview   Renders one frame per look on the same frame, plus the original, side by side:
            assets/grade_preview.jpg and assets/grade_preview_<id>.png (id = original|clean|warm|dark)
apply     Stores {id, filter} in project.json under "grade". assemble.py applies it with -vf. "none" clears it.

Chains use only eq, colorbalance and curves (ffmpeg 4+). Colours are measured in OpenCV HSV: hue 0-179, skin ~5-25,
lower = redder, higher = more yellow. Values < 0 after unwrapping mean magenta side.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

FPS = 30
FRAME_POINTS = (0.10, 0.30, 0.50, 0.70, 0.90)
GRADE_IDS = ("clean", "warm", "dark")
STRENGTHS = (1.0, 0.8, 0.6, 0.4, 0.2, 0.0)
SKIN_LUMA_RANGE = (85.0, 150.0)       # only correct exposure when the skin sits outside this
HUE_MIN_SHIFT, HUE_MAX_SHIFT = -1.0, 6.0
SAT_MAX_RATIO = {"clean": 1.15, "warm": 1.15, "dark": 1.25}
CLIP_TOL = 0.002
LOW_TOL = {"clean": 0.01, "warm": 0.01, "dark": 0.04}
FACE_LUMA_MIN, FACE_LUMA_MAX = 70.0, 190.0
VERIFY_W, VERIFY_H = 540, 960         # verification runs on half-size frames: colour is identical, 4x faster
NAMES = {"clean": "Clean", "warm": "Warm", "dark": "Dark and punchy"}


def die(msg, fix=""):
    print(f"grade: {msg}" + (f"\n  Fix: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(1)


def run(cmd, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        die(f"{os.path.basename(cmd[0])} failed: {r.stderr.strip()[-400:]}", "run doctor.py to check ffmpeg")
    return r


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def need_cv2():
    if cv2 is None:
        die("OpenCV is missing", "install it into the Reel Room venv: pip install opencv-python-headless")


# ---------------------------------------------------------------- frames + face
def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path])
    return float(r.stdout.strip())


def extract_frame(src, t, out, scale=None):
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1"]
    if scale:
        cmd += ["-vf", f"scale={scale[0]}:{scale[1]}:flags=area"]
    run(cmd + [out])


def find_face(img, t, segs, facepos):
    """Face box (x, y, w, h) in this image's pixels. facepos is in aroll pixels (1080x1920)."""
    ih, iw = img.shape[:2]
    k = iw / 1080.0
    f = int(t * FPS)
    seg = next((s for s in segs if s["frame"] <= f < s["frame"] + s["frames"]), None)
    fp = (facepos or {}).get(seg["id"]) if seg else None
    if fp:
        h = fp["h"] * k
        return int(fp["cx"] * k - 0.40 * h), int(fp["cy"] * k - 0.5 * h), int(0.8 * h), int(h)
    casc = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    g = cv2.cvtColor(cv2.resize(img, (iw // 2, ih // 2)), cv2.COLOR_BGR2GRAY)
    faces = casc.detectMultiScale(g, 1.1, 5, minSize=(40, 40)) if not casc.empty() else []
    if len(faces):
        x, y, w, h = max(faces, key=lambda f_: f_[2] * f_[3])
        return int(x * 2), int(y * 2), int(w * 2), int(h * 2)
    return None


# ---------------------------------------------------------------- measuring
def luma709(bgr):
    b, g, r = [bgr[..., i].astype(np.float32) for i in range(3)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def measure(img, face):
    """Everything the grader needs from one frame."""
    ih, iw = img.shape[:2]
    L = luma709(img)
    out = {"luma": float(L.mean()), "p1": float(np.percentile(L, 1)), "p99": float(np.percentile(L, 99)),
           "clip_hi": float((L >= 250).mean()), "clip_lo": float((L <= 5).mean())}
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    keep = (hsv[..., 1] < 0.35 * 255) & (hsv[..., 2] > 0.1 * 255) & (hsv[..., 2] < 0.97 * 255)
    if face:
        x, y, w, h = face
        keep[max(0, y - h // 4):y + h + h // 4, max(0, x - w // 3):x + w + w // 3] = False
    if keep.sum() > 2000:
        px = img[keep].astype(np.float32).mean(axis=0)               # B, G, R means over neutral-ish pixels
        out["cast_rg"], out["cast_bg"] = float(px[2] / px[1]), float(px[0] / px[1])
    else:
        out["cast_rg"] = out["cast_bg"] = 1.0
    out["skin"] = skin_stats(img, face, hsv)
    return out


def skin_stats(img, face, hsv):
    if not face:
        return None
    x, y, w, h = face
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, int(cx - 0.3 * w)), max(0, int(cy - 0.3 * h))
    x1, y1 = int(cx + 0.3 * w), int(cy + 0.3 * h)
    roi, roi_hsv = img[y0:y1, x0:x1], hsv[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    m = ((ycc[..., 1] >= 133) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 77) & (ycc[..., 2] <= 130) & (ycc[..., 0] > 25))
    hue = roi_hsv[..., 0].astype(np.float32)
    hue = np.where(hue > 90, hue - 180, hue)                         # unwrap: magenta side becomes negative
    m &= (hue > -15) & (hue < 30)
    if m.sum() < 150:
        return None
    L = luma709(roi)
    return {"hue": float(np.median(hue[m])), "sat": float(np.median(roi_hsv[..., 1][m]) / 255.0),
            "luma": float(np.median(L[m])), "px": int(m.sum())}


def med(vals):
    vals = [v for v in vals if v is not None]
    return float(np.median(vals)) if vals else None


# ---------------------------------------------------------------- chains
def fmt(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


def build_chain(kind, m, k):
    """ffmpeg -vf chain for `kind`, deltas scaled by strength k (0 = identity). Only eq, colorbalance, curves."""
    parts = []
    # exposure: gamma from skin luma (or frame luma), only when outside the healthy range
    ref = m["skin_luma"] if m["skin_luma"] else m["luma"]
    lo, hi = SKIN_LUMA_RANGE if m["skin_luma"] else (95.0, 150.0)
    desired = min(max(ref, lo), hi)
    gamma = 1.0
    if desired != ref and ref > 1:
        gamma = math.log(ref / 255.0) / math.log(desired / 255.0)
        gamma = min(max(gamma, 0.88), 1.18)
    gamma = 1.0 + (gamma - 1.0) * k
    eq = {"gamma": gamma}
    # white balance on the warm/cool axis only, dead band 3 %, never more than 0.04 of colourbalance
    wb_r = wb_b = 0.0
    dev = (m["cast_rg"] - m["cast_bg"]) / 2.0                          # >0 = frame leans warm, <0 = leans cool
    if abs(dev) > 0.03:
        c = max(-0.04, min(0.04, -dev * 0.4)) * k
        wb_r, wb_b = c, -c
    cb = {"rm": wb_r, "bm": wb_b}
    curve = None
    if m["clip_hi"] > 0.002:                                           # whites already clip: roll the top off
        curve = [(0, 0), (0.5, 0.5), (0.85, 0.85 - 0.02 * k), (1, 1 - 0.05 * k)]
    if kind == "warm":
        cb["rm"] += 0.018 * k
        cb["gm"] = cb.get("gm", 0) + 0.007 * k                        # red + green = golden, not red
        cb["bm"] -= 0.035 * k
        cb["rh"] = 0.012 * k
        cb["bh"] = -0.025 * k
        eq["saturation"] = 1.0 + 0.04 * k
    if kind == "dark":
        # Moodier, not murkier: pivot the curve on the skin brightness so the face keeps its light while
        # the shadows deepen and the bright room behind it comes down (this is what keeps whites from clipping).
        pv = min(max((ref if ref > 1 else 90.0) / 255.0, 0.25), 0.5)
        eq["gamma"] = eq["gamma"] * (1.0 - 0.02 * k)
        eq["saturation"] = 1.0 - 0.04 * k
        hi_x = pv + 0.35 * (1 - pv)
        curve = [(0, 0), (0.45 * pv, 0.45 * pv - 0.05 * k), (pv, pv), (hi_x, hi_x - 0.07 * k), (1, 1 - 0.07 * k)]
    eqs = ":".join(f"{n}={fmt(v)}" for n, v in eq.items() if abs(v - (1.0 if n != "brightness" else 0.0)) > 1e-4)
    cbs = ":".join(f"{n}={fmt(v)}" for n, v in cb.items() if abs(v) > 1e-4)
    if eqs:
        parts.append("eq=" + eqs)
    if cbs:
        parts.append("colorbalance=" + cbs)
    if curve:
        parts.append("curves=all='" + " ".join(f"{fmt(x)}/{fmt(y)}" for x, y in curve) + "'")
    return ",".join(parts)


def apply_chain(src_png, chain, dst_png):
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src_png]
    if chain:
        cmd += ["-vf", chain]
    run(cmd + ["-frames:v", "1", dst_png])


def verify(chain, base, small, faces, tmp, kind):
    """Apply chain to the half-size frames, remeasure, return (ok, report, reasons)."""
    deltas, sats, chi, clo, fl = [], [], [], [], []
    for i, (png, face) in enumerate(zip(small, faces)):
        dst = os.path.join(tmp, f"v_{kind}_{i}.png")
        apply_chain(png, chain, dst)
        after = measure(cv2.imread(dst), face)
        before = base[i]
        if after["skin"] and before["skin"]:
            deltas.append(after["skin"]["hue"] - before["skin"]["hue"])
            sats.append(after["skin"]["sat"] / max(before["skin"]["sat"], 1e-3))
            fl.append(after["skin"]["luma"])
        else:
            fl.append(after["luma"])
        chi.append(after["clip_hi"] - before["clip_hi"])
        clo.append(after["clip_lo"] - before["clip_lo"])
    rep = {"skin_hue_shift": med(deltas) or 0.0, "skin_sat_ratio": med(sats) or 1.0,
           "clip_hi_added": float(max(chi)), "clip_lo_added": float(max(clo)), "face_luma": med(fl)}
    why = []
    if rep["skin_hue_shift"] < HUE_MIN_SHIFT:
        why.append("skin pushed toward red/magenta")
    if rep["skin_hue_shift"] > HUE_MAX_SHIFT:
        why.append("skin pushed too far toward yellow")
    if rep["skin_sat_ratio"] > SAT_MAX_RATIO[kind]:
        why.append("skin colour too strong")
    if rep["clip_hi_added"] > CLIP_TOL:
        why.append("highlights clip")
    if rep["clip_lo_added"] > LOW_TOL[kind]:
        why.append("shadows crushed")
    if not (FACE_LUMA_MIN <= rep["face_luma"] <= FACE_LUMA_MAX):
        why.append("face too dark or too bright")
    return not why, rep, why


def fit(kind, m, base, small, faces, tmp):
    """Strongest strength that passes every rule. Strength 0 is the identity and always passes."""
    clamped = []
    for k in STRENGTHS:
        chain = build_chain(kind, m, k)
        if not chain:
            return chain, k, {"skin_hue_shift": 0.0}, clamped
        ok, rep, why = verify(chain, base, small, faces, tmp, kind)
        if ok:
            return chain, k, rep, clamped
        clamped.append(f"{int(k * 100)}%: {', '.join(why)}")
    return "", 0.0, {"skin_hue_shift": 0.0}, clamped


def reason(kind, m, chain, k, clamped):
    dark = m["skin_luma"] is not None and m["skin_luma"] < SKIN_LUMA_RANGE[0] or (m["skin_luma"] is None and m["luma"] < 95)
    bright = m["skin_luma"] is not None and m["skin_luma"] > SKIN_LUMA_RANGE[1]
    dev = (m["cast_rg"] - m["cast_bg"]) / 2.0
    fixes = []
    if "gamma" in chain and kind == "clean":
        fixes.append("lifts a dim face" if dark else "eases down a bright face" if bright else "fine-tunes exposure")
    if kind == "clean":
        if abs(dev) > 0.03 and "colorbalance" in chain:
            fixes.append("evens out a cool cast" if dev < 0 else "evens out a warm cast")
        if "curves" in chain:
            fixes.append("rolls off the brightest whites")
        base = ("Your footage already looks healthy, so this changes almost nothing."
                if not fixes else "Correction only: " + ", ".join(fixes) + ".")
        return base + " Skin stays true."
    if kind == "warm":
        s = "A golden, editorial warmth in the mids and highlights"
        s += ", with a small lift for a dim face" if dark else ""
        return s + ". Skin stays natural, never pushed red."
    s = "More contrast and deeper shadows for a punchy look" + (", with the face kept lit" if not dark else ", with the face lifted so it stays readable")
    return s + ". Whites are protected from clipping."


# ---------------------------------------------------------------- commands
def paths(project):
    return {"aroll": os.path.join(project, "assets", "aroll.mp4"),
            "work": os.path.join(project, "work", "grade"),
            "json": os.path.join(project, "work", "grade.json"),
            "assets": os.path.join(project, "assets"),
            "project": os.path.join(project, "project.json")}


def cmd_analyze(project):
    need_cv2()
    P = paths(project)
    if not os.path.isfile(P["aroll"]):
        die(f"{P['aroll']} not found", "run assemble.py first so there is footage to grade")
    segs = load_json(os.path.join(project, "segments.json"), [])
    facepos = load_json(os.path.join(project, "work", "facepos.json"))
    os.makedirs(P["work"], exist_ok=True)
    dur = duration(P["aroll"])
    times = [round(dur * p, 2) for p in FRAME_POINTS]
    full, small, faces, base = [], [], [], []
    for i, t in enumerate(times):
        fpng, spng = os.path.join(P["work"], f"frame_{i}.png"), os.path.join(P["work"], f"small_{i}.png")
        extract_frame(P["aroll"], t, fpng)
        img = cv2.imread(fpng)
        face = find_face(img, t, segs, facepos)
        sm = cv2.resize(img, (VERIFY_W, VERIFY_H), interpolation=cv2.INTER_AREA)
        cv2.imwrite(spng, sm)
        k = VERIFY_W / img.shape[1]
        sface = tuple(int(v * k) for v in face) if face else None
        full.append(fpng)
        small.append(spng)
        faces.append(sface)
        base.append(measure(sm, sface))
    skins = [b["skin"] for b in base if b["skin"]]
    m = {"luma": med([b["luma"] for b in base]), "p1": med([b["p1"] for b in base]),
         "p99": med([b["p99"] for b in base]), "clip_hi": med([b["clip_hi"] for b in base]),
         "clip_lo": med([b["clip_lo"] for b in base]), "cast_rg": med([b["cast_rg"] for b in base]),
         "cast_bg": med([b["cast_bg"] for b in base]),
         "skin_hue": med([s["hue"] for s in skins]), "skin_sat": med([s["sat"] for s in skins]),
         "skin_luma": med([s["luma"] for s in skins]), "faces_found": sum(1 for f in faces if f)}
    options = []
    for kind in GRADE_IDS:
        chain, k, rep, clamped = fit(kind, m, base, small, faces, P["work"])
        options.append({"id": kind, "name": NAMES[kind], "reason": reason(kind, m, chain, k, clamped),
                        "filter": chain, "strength": k, "checks": {a: round(b, 4) for a, b in rep.items() if b is not None},
                        "clamped": clamped})
    result = {"frames": [{"t": t, "png": f} for t, f in zip(times, full)], "measurements": m, "options": options}
    save_json(P["json"], result)
    return result


def side_by_side(panels, out_jpg):
    from PIL import Image, ImageDraw, ImageFont
    pw, ph, bar = 405, 720, 44
    sheet = Image.new("RGB", (pw * len(panels), ph + bar), (18, 18, 20))
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for i, (label, png) in enumerate(panels):
        im = Image.open(png).convert("RGB").resize((pw, ph), Image.LANCZOS)
        sheet.paste(im, (i * pw, bar))
        d.text((i * pw + 12, 10), label, fill=(240, 240, 240), font=font)
    sheet.save(out_jpg, quality=90)


def cmd_preview(project, t):
    need_cv2()
    P = paths(project)
    data = load_json(P["json"])
    if not data:
        die("no analysis yet", f"run: grade.py {project} analyze")
    if t is None:
        t = data["frames"][2]["t"]
    os.makedirs(P["assets"], exist_ok=True)
    src = os.path.join(P["assets"], "grade_preview_original.png")
    extract_frame(P["aroll"], t, src)
    panels = [("Original", src)]
    for o in data["options"]:
        out = os.path.join(P["assets"], f"grade_preview_{o['id']}.png")
        apply_chain(src, o["filter"], out)
        o["preview"] = os.path.relpath(out, project)
        panels.append((o["name"], out))
    jpg = os.path.join(P["assets"], "grade_preview.jpg")
    side_by_side(panels, jpg)
    data["preview"] = {"t": t, "sheet": os.path.relpath(jpg, project)}
    save_json(P["json"], data)
    return data


def cmd_apply(project, gid):
    P = paths(project)
    proj = load_json(P["project"], {})
    if gid == "none":
        proj["grade"] = None
    else:
        data = load_json(P["json"])
        opt = next((o for o in (data or {}).get("options", []) if o["id"] == gid), None)
        if not opt:
            die(f"no analysed grade called '{gid}'", f"run: grade.py {project} analyze, then apply one of {', '.join(GRADE_IDS)}")
        proj["grade"] = {"id": opt["id"], "filter": opt["filter"]}
    save_json(P["project"], proj)
    return {"grade": proj["grade"]}


def main():
    ap = argparse.ArgumentParser(description="Reel Room colour grade")
    ap.add_argument("project")
    ap.add_argument("action", choices=["analyze", "preview", "apply"])
    ap.add_argument("id", nargs="?", help="for apply: clean | warm | dark | none")
    ap.add_argument("--t", type=float, help="preview: time in seconds (default: middle analysis frame)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    project = os.path.abspath(a.project)
    if not os.path.isdir(project):
        die(f"project folder not found: {project}")
    if a.action == "analyze":
        res = cmd_analyze(project)
    elif a.action == "preview":
        res = cmd_preview(project, a.t)
    else:
        if not a.id:
            die("apply needs a grade id", "grade.py <project> apply clean|warm|dark|none")
        res = cmd_apply(project, a.id)
    if a.json:
        print(json.dumps(res, indent=2))
        return
    if a.action == "apply":
        g = res["grade"]
        print("grade cleared" if not g else f"grade '{g['id']}' saved to project.json")
        return
    m = res.get("measurements")
    if m and a.action == "analyze":
        sk = f"skin hue {m['skin_hue']:.1f}, skin luma {m['skin_luma']:.0f}" if m["skin_luma"] else "no face found"
        print(f"frame luma {m['luma']:.0f}, clip {m['clip_hi'] * 100:.2f}% hi / {m['clip_lo'] * 100:.2f}% lo, "
              f"cast r/g {m['cast_rg']:.2f} b/g {m['cast_bg']:.2f}, {sk}")
    for o in res["options"]:
        print(f"{o['id']:<6} {o['reason']}\n       strength {o['strength']:.1f}  {o['checks']}\n       -vf {o['filter'] or '(no change)'}")
        if o.get("clamped"):
            print(f"       backed off: {' / '.join(o['clamped'])}")
    if a.action == "preview":
        print("preview:", os.path.join(project, res["preview"]["sheet"]))


if __name__ == "__main__":
    main()
