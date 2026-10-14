#!/usr/bin/env python3
"""Reel Room style scan: watch a few reels, describe the editing system, match it to the style catalog.

  python style_scan.py --files <folder_or_videos ...> [--mode creator|vibe] [--name NAME] [--n 5] [--out DIR] [--json]
  python style_scan.py <@handle | reel URLs ...> [--cookies-from-browser chrome] [--mode ...] [--n 5] [--json]
  python style_scan.py --files ... --basic          # pixel-only scan, no AI key needed

Inputs
  --files   local videos or a folder (most reliable: the user saves 3 to 5 reels and gives the paths).
  online    @handle or reel links, downloaded with yt-dlp. Instagram often blocks anonymous downloads: pass
            --cookies-from-browser chrome (or safari, firefox, edge, brave). If it still fails, ask for files.
Modes   creator = a reference creator: the system that repeats across their reels.
        vibe    = "analyze my Instagram": the user's own look, and styles that fit it.

How it works
  1. Pixels (style_pixels.py, offline, cheap): cuts per second, text bands, face size, split seam, palette, pace.
  2. AI (style_ai.py): Gemini watches each reel (uploaded to the Gemini Files API, deleted right after) and answers
     a strict JSON editor's breakdown: layout, captions, title, graphics, cutout, colour, pacing, sound, signature moves.
  3. A second text-only Gemini call aggregates the reels into a card: what is consistent, what varies, and the top 3
     styles from styles/catalog.json (ids validated) with a reason grounded in what was seen, plus a confidence.
  No key (or --basic): pixel numbers only, mapped to the current catalog ids, labelled "Basic scan (no AI key)".

Writes <out>/style_card.json and <out>/contact_sheet.jpg. Never prints the API key.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

import style_ai
import style_pixels as px

BASIC_CAP = 60                      # a pixel-only guess never claims more than a 60% fit
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IG_HELP = ("Instagram often blocks downloads. Easiest fix: save 3 to 5 reels to your computer and send the file "
           "paths to Claude in the chat. Or retry with --cookies-from-browser chrome so yt-dlp uses your "
           "logged-in browser.")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def die(msg, fix="", code=1):
    print(f"style_scan: {msg}" + (f"\n  Fix: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(code)


def ramp(x, lo, hi):
    if x is None:
        return 0.0
    return float(min(1.0, max(0.0, (x - lo) / (hi - lo)))) if hi != lo else float(x >= hi)


def load_catalog():
    with open(os.path.join(SK, "styles", "catalog.json"), encoding="utf-8") as f:
        return [s for s in json.load(f)["styles"] if not s.get("coming")]


# ---------------------------------------------------------------- getting videos
def find_ytdlp():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    home = os.path.expanduser("~/.reel-room/venv")
    for cand in (os.path.join(home, "bin", "yt-dlp"), os.path.join(home, "Scripts", "yt-dlp.exe")):
        if os.path.exists(cand):
            return [cand]
    return None


def target_urls(items):
    urls = []
    for it in items:
        if re.match(r"https?://", it):
            urls.append(it)
        else:
            handle = it.lstrip("@").strip("/")
            if not re.fullmatch(r"[A-Za-z0-9._]{1,40}", handle):
                die(f"'{it}' is not a handle or a link", "use @name or a full https:// link")
            urls.append(f"https://www.instagram.com/{handle}/reels/")
    return urls


def download(items, n, cookies, workdir):
    ytdlp = find_ytdlp()
    if not ytdlp:
        die("yt-dlp is not installed", "run doctor.py, or save the reels and send the file paths")
    for url in target_urls(items):
        cmd = ytdlp + ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--playlist-end", str(n), "--max-downloads", str(n),
                       "--no-warnings", "--restrict-filenames", "--socket-timeout", "30", "--merge-output-format", "mp4",
                       "--max-filesize", "300M", "-o", os.path.join(workdir, "%(autonumber)03d_%(id)s.%(ext)s")]
        if cookies:
            cmd += ["--cookies-from-browser", cookies]
        log(f"downloading up to {n} videos from {url}")
        r = subprocess.run(cmd + [url], capture_output=True, text=True, timeout=1800)
        if r.returncode not in (0, 101):          # 101 = stopped by --max-downloads, which is success here
            err = ((r.stderr or "").strip().splitlines() or ["unknown error"])[-1]
            log(f"  could not download from {url}: {err[:200]}")
            log("  " + (IG_HELP if "instagram" in url else "Check the link, or save the videos and use --files."))
    got = [p for p in sorted(glob.glob(os.path.join(workdir, "*"))) if p.lower().endswith(VIDEO_EXT)]
    return got[:n]


def local_videos(paths, n):
    vids = []
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            vids += sorted((os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(VIDEO_EXT)),
                           key=lambda x: -os.path.getmtime(x))
        elif os.path.isfile(p):
            vids.append(p)
        else:
            log(f"skipping, not found: {p}")
    return vids[:n]


# ---------------------------------------------------------------- basic (pixel-only) match
def basic_match(per, catalog):
    """Pixel-only guess over the CURRENT catalog ids. Weak by nature: it cannot read text or see cutouts."""
    def a(g):
        return px.agg(per, g)
    cut = a(lambda p: p["cuts_per_sec"]) or 0
    face = a(lambda p: p["framing"]["face_frac"]) or 0
    split = a(lambda p: p["framing"]["split_frac"]) or 0
    tf = a(lambda p: p["text"]["frames_with_text"]) or 0
    ta = a(lambda p: p["text"]["area_pct"]) or 0
    big = a(lambda p: p["text"]["big_type_frac"]) or 0
    top = a(lambda p: p["text"]["band_share"]["top"] + p["text"]["band_share"]["upper"]) or 0
    low = a(lambda p: p["text"]["band_share"]["lower"] + p["text"]["band_share"]["bottom"]) or 0
    bright = a(lambda p: p["look"]["brightness"]) or 128
    rules = {
        "split-deck": [(0.6, ramp(split, 0.1, 0.5), "a hard split near the middle is on screen a lot"),
                       (0.2, ramp(tf, 0.2, 0.6), "text is on screen most of the time"),
                       (0.2, ramp(cut, 0.15, 0.4), "it cuts steadily")],
        "motion-editorial": [(0.4, ramp(split, 0.05, 0.35), "the frame is often split"),
                             (0.4, ramp(big, 0.05, 0.3), "big type shows up often"),
                             (0.2, ramp(ta, 1.0, 5.0), "type covers a lot of the screen")],
        "clean-talk": [(0.5, ramp(face, 0.5, 0.9), "the speaker is on screen almost all the time"),
                       (0.3, 1 - ramp(ta, 1.5, 5.0), "very little text on screen"),
                       (0.2, 1 - ramp(split, 0.05, 0.3), "full frame, no split")],
        "list-stack": [(0.5, ramp(top, 0.35, 0.7), "text sits above the speaker's head"),
                       (0.3, ramp(tf, 0.5, 0.9), "text stays on screen"),
                       (0.2, ramp(face, 0.4, 0.8), "the speaker stays in shot")],
        "editorial-ui": [(0.5, ramp(big, 0.1, 0.4), "huge type is common"),
                         (0.3, ramp(face, 0.4, 0.8), "the speaker carries the shot"),
                         (0.2, ramp(cut, 0.3, 0.7), "fast cutting")],
        "floating-cards": [(0.4, ramp(face, 0.5, 0.9), "the speaker is on screen most of the time"),
                           (0.3, ramp(bright, 120, 170), "a bright look"),
                           (0.3, ramp(tf, 0.3, 0.7), "small text appears often")],
        "carousel-slideup": [(0.5, ramp(low, 0.4, 0.8), "text cards sit in the lower half"),
                             (0.5, ramp(ta, 2.0, 8.0), "text-heavy cards")],
        "desk-demo": [(0.6, 1 - ramp(face, 0.3, 0.8), "the speaker is often off screen"),
                      (0.4, ramp(ta, 1.5, 6.0), "screens full of text")],
    }
    out = []
    for s in catalog:
        rs = rules.get(s["id"])
        if not rs:
            continue
        score = sum(w * v for w, v, _ in rs)
        why = [m for _, v, m in rs if v >= 0.5]
        out.append({"id": s["id"], "fit": int(round(score * BASIC_CAP)),
                    "reason": ("Basic scan: " + ", ".join(why) + ".") if why else "Basic scan: weak signal."})
    return sorted(out, key=lambda x: -x["fit"])[:3]


def pixel_numbers(per):
    def a(g):
        return px.agg(per, g)
    wpm = [p["pace"]["words_per_min"] for p in per if p["pace"]["words_per_min"]]
    return {"cuts_per_sec": round(a(lambda p: p["cuts_per_sec"]) or 0, 3),
            "face_frac": round(a(lambda p: p["framing"]["face_frac"]) or 0, 3),
            "split_frac": round(a(lambda p: p["framing"]["split_frac"]) or 0, 3),
            "text_frames": round(a(lambda p: p["text"]["frames_with_text"]) or 0, 3),
            "brightness": round(a(lambda p: p["look"]["brightness"]) or 0, 1),
            "words_per_min": round(sum(wpm) / len(wpm)) if wpm else None}


# ---------------------------------------------------------------- cards
def ai_card(vids, per, catalog, key, mode):
    """Gemini path. Returns (card, None) or (None, reason) when no reel could be watched."""
    t0 = time.time()
    watched = style_ai.watch_all(vids, key)
    reels = [dict(j, file=os.path.basename(p)) for p, j, _, _, _ in watched if isinstance(j, dict)]
    if not reels:
        errs = [e for *_, e in watched if e]
        if errs and errs[0].kind == "auth":
            raise errs[0]
        return None, str(errs[0]) if errs else "no reel could be watched"
    j, m2, t2 = style_ai.match(reels, pixel_numbers(per), catalog, key, mode)
    matches = style_ai.clean_matches(j.get("matches"), catalog)
    if len(matches) < 3:                     # always hand back 3 picks: fill from the pixel guess, marked as such
        have = {x["id"] for x in matches}
        matches += [x for x in basic_match(per, catalog) if x["id"] not in have][:3 - len(matches)]
    dn = style_ai.no_dash
    best = matches[0]["fit"] if matches else 0
    no_fit = j.get("no_fit") or (f"Nothing in the catalog is a close match (best fit {best}%)." if best < 55 else None)
    used = sorted({m for _, _, m, _, _ in watched if m} | {m2})
    return {"engine": "ai", "engine_label": "AI scan: Gemini watched the reels", "models": used,
            "summary": dn(str(j.get("summary", ""))),
            "system": [{"label": str(r.get("label", "")), "text": dn(str(r.get("text", "")))}
                       for r in j.get("system", []) if isinstance(r, dict)],
            "consistent": [dn(str(x)) for x in j.get("consistent", [])][:8],
            "varies": [dn(str(x)) for x in j.get("varies", [])][:6],
            "matches": matches,
            "confidence": j.get("confidence") if j.get("confidence") in ("high", "medium", "low") else "medium",
            "no_fit": dn(str(no_fit)) if no_fit else None, "per_reel": reels,
            "cost": {"tokens": sum(t or 0 for _, _, _, t, _ in watched) + (t2 or 0),
                     "seconds": round(time.time() - t0, 1)}}, None


def basic_card(per, catalog, why):
    n = pixel_numbers(per)
    notes = [f"A new shot every {1 / n['cuts_per_sec']:.1f} s." if n["cuts_per_sec"] else "Almost no cuts.",
             f"Speaker on screen {round(n['face_frac'] * 100)}% of the time, text on screen "
             f"{round(n['text_frames'] * 100)}% of the time."]
    return {"engine": "basic", "engine_label": "Basic scan (no AI key)", "basic_reason": why,
            "summary": "Measured from the pixels only. It cannot read captions or see cut-outs, so treat the picks "
                       "as a rough guess.",
            "system": [], "consistent": [], "varies": [], "matches": basic_match(per, catalog),
            "confidence": "low", "no_fit": None, "notes": notes, "setup": style_ai.KEY_HELP}


def finish(card, name, mode, per, rows, out, t0):
    sheet = os.path.join(out, "contact_sheet.jpg")
    px.contact_sheet(rows, sheet)
    card.update({"name": name, "mode": mode, "videos": len(per), "palette": px.merge_palettes(per),
                 "recommended_styles": [m["id"] for m in card["matches"]],
                 "recommended_detail": [{"id": m["id"], "score": round(m["fit"] / 100, 2),
                                         "because": [m["reason"]] if m["reason"] else []} for m in card["matches"]],
                 "metrics": {"summary": pixel_numbers(per), "per_video": per}, "contact_sheet": sheet,
                 "seconds_total": round(time.time() - t0, 1)})
    with open(os.path.join(out, "style_card.json"), "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)
    return card


def print_card(card, out):
    print(f"{card['name']}: {card['engine_label']}, {card['videos']} videos -> {out}")
    if card["engine"] == "basic":
        print(f"  ({card['basic_reason']}) {style_ai.KEY_HELP}")
    print("  " + card["summary"])
    for r in card.get("system", []):
        print(f"  {r['label']}: {r['text']}")
    for m in card["matches"]:
        print(f"  {m['id']:<18} {m['fit']:>3}%  {m['reason']}")
    if card.get("no_fit"):
        print("  " + card["no_fit"])
    cost = card.get("cost")
    print(f"  confidence {card['confidence']}, {card['seconds_total']} s" + (f", {cost['tokens']} tokens" if cost else ""))


def main():
    ap = argparse.ArgumentParser(description="Reel Room style scan")
    ap.add_argument("targets", nargs="*", help="@handle or reel/video URLs")
    ap.add_argument("--files", nargs="+", help="local videos or a folder (most reliable)")
    ap.add_argument("--n", type=int, default=5, help="how many videos (default 5, 3 to 5 is plenty)")
    ap.add_argument("--cookies-from-browser", dest="cookies", help="chrome, safari, firefox, edge or brave (Instagram)")
    ap.add_argument("--out", help="output folder (default ~/.reel-room/style_scans/<name>)")
    ap.add_argument("--name", help="name for the card (default: handle or folder name)")
    ap.add_argument("--mode", choices=["vibe", "creator"], default="vibe")
    ap.add_argument("--max-seconds", type=float, default=75.0)
    ap.add_argument("--basic", action="store_true", help="pixel-only scan, no AI")
    ap.add_argument("--json", action="store_true", help="print the card as JSON (per-reel detail stays in style_card.json)")
    a = ap.parse_args()
    t0 = time.time()
    if px.cv2 is None:
        die("OpenCV is missing", "run doctor.py (it installs opencv-python-headless)")
    if not a.targets and not a.files:
        die("nothing to scan", "send 3 to 5 reel files (--files), or a handle or reel links")
    name = a.name or (a.targets[0].lstrip("@").rstrip("/").split("/")[-1] if a.targets
                      else os.path.basename(os.path.normpath(a.files[0])))
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:40] or "scan"
    out = os.path.abspath(os.path.expanduser(a.out)) if a.out else os.path.expanduser(f"~/.reel-room/style_scans/{name}")
    os.makedirs(out, exist_ok=True)
    if a.files:
        vids = local_videos(a.files, a.n)
    else:
        dl = os.path.join(out, "downloads")
        os.makedirs(dl, exist_ok=True)
        vids = download(a.targets, a.n, a.cookies, dl)
    if not vids:
        die("no videos to scan", IG_HELP if a.targets else "put .mp4 or .mov files in the folder")
    catalog = load_catalog()
    per, rows, ok = [], [], []
    for i, v in enumerate(vids, 1):
        log(f"[{i}/{len(vids)}] measuring {os.path.basename(v)}")
        try:
            m, thumbs = px.analyze_video(v, a.max_seconds)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            log(f"  skipped: {e}")
            continue
        per.append(m)
        rows.append((os.path.basename(v), thumbs))
        ok.append(v)
    if not per:
        die("none of the videos could be read", "check that ffmpeg is installed (doctor.py) and the files play")
    key = None if a.basic else style_ai.load_key()
    card, why = None, ("a pixel-only scan was asked for" if a.basic else "no Gemini key found")
    if key:
        log(f"Gemini is watching {len(ok)} reels (about 20 to 60 s each, 3 at a time)")
        try:
            card, err = ai_card(ok, per, catalog, key, a.mode)
            why = err or why
        except style_ai.GeminiError as e:
            why = "the Gemini key was refused, check it" if e.kind == "auth" else f"Gemini did not answer ({e.kind})"
            log(f"  AI scan failed: {e}")
    if card is None:
        card = basic_card(per, catalog, why)
    card = finish(card, name, a.mode, per, rows, out, t0)
    if a.json:
        slim = {k: v for k, v in card.items() if k != "per_reel"}
        slim["metrics"] = {"summary": card["metrics"]["summary"]}
        print(json.dumps(slim, indent=2, ensure_ascii=False))
    else:
        print_card(card, out)


if __name__ == "__main__":
    main()
