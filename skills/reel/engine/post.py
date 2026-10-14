#!/usr/bin/env python3
"""Reel Room post: upload a finished reel + cover to Zernio and publish, schedule or save a draft.

Generalised from zernio_post_v0.py. Zernio is optional: without ZERNIO_API_KEY this prints the affiliate link and the
manual phone steps instead (https://zernio.link/emeka-ajufo).

  python post.py --project <project> --mode draft                      # newest *-share.mp4 + its cover + caption.txt
  python post.py --video reel.mp4 --cover cover.png --caption-file cap.txt --mode now
  python post.py --video reel.mp4 --cover c.png --caption "..." --mode schedule --at 2026-10-12T12:00:00 --tz America/New_York
  python post.py --video reel.mp4 --cover c.png --caption-file cap.txt --mode draft --trial        # Instagram trial reel
  python post.py --carousel --image a.png b.png c.png --caption-file cap.txt --mode draft          # carousel (images and/or videos)
  python post.py ... --dry-run                                         # build the payload, no network, nothing uploaded
  python post.py --list-accounts                                       # show connected accounts (needs the key)

Environment / config (the key is only ever read from the environment and is never printed)
  ZERNIO_API_KEY                    required for real posting
  ZERNIO_INSTAGRAM_ACCOUNT_ID       Instagram account id; or --account-id; or ~/.reel-room/zernio.json
                                    {"instagramAccountId": "..."}; or, if the key's workspace has exactly one
                                    Instagram account, it is picked automatically
Modes   draft    nothing goes public (default)    now   publish immediately    schedule   needs --at and --tz
Trial   --trial adds platformSpecificData.trialParams {graduationStrategy: MANUAL | SS_PERFORMANCE}. A trial reel
        is shown to non-followers first. MANUAL: you graduate it in the Instagram app. SS_PERFORMANCE: Instagram
        graduates it automatically when it performs well. Trial reels cannot be carousels.
Cover   Instagram wants a JPEG cover: a PNG cover is converted to JPEG next to the original before upload.
Exit codes  0 ok, 1 error, 3 no API key (manual steps printed)
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://zernio.com/api/v1"
AFFILIATE = "https://zernio.link/emeka-ajufo"
IG_MAX_REEL_S, IG_MAX_VIDEO_BYTES, IG_MAX_CAPTION, IG_MAX_HASHTAGS, MAX_CAROUSEL = 90, 300_000_000, 2200, 30, 10
IMG_EXT, VID_EXT = (".png", ".jpg", ".jpeg", ".webp"), (".mp4", ".mov", ".m4v")
CTYPE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4"}
KEY_ENV = "ZERNIO_API_KEY"


def die(msg, fix="", code=1):
    print(f"post: {msg}" + (f"\n  Fix: {fix}" if fix else ""), file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- API (the key never leaves the Authorization header)
def call(method, path, body=None):
    key = os.environ.get(KEY_ENV, "")
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400].replace(key, "***") if key else ""
        hint = "Check ZERNIO_API_KEY." if e.code in (401, 403) else ""
        die(f"{method} {path} failed with {e.code}: {detail}", hint)
    except urllib.error.URLError as e:
        die(f"could not reach Zernio ({e.reason})", "check your internet connection and try again")


def upload(path):
    ext = os.path.splitext(path)[1].lower()
    ctype = CTYPE.get(ext, "application/octet-stream")
    p = call("POST", "/media/presign", {"filename": os.path.basename(path), "contentType": ctype,
                                        "size": os.path.getsize(path)})
    p = p.get("data", p)
    with open(path, "rb") as f:
        req = urllib.request.Request(p["uploadUrl"], data=f.read(), method="PUT", headers={"Content-Type": ctype})
        try:
            urllib.request.urlopen(req, timeout=900).read()
        except (urllib.error.URLError, OSError) as e:
            die(f"upload of {os.path.basename(path)} failed: {e}")
    return p["publicUrl"]


def instagram_account(arg):
    acc = arg or os.environ.get("ZERNIO_INSTAGRAM_ACCOUNT_ID") or os.environ.get("ZERNIO_ACCOUNT_ID")
    if not acc:
        cfg = os.path.expanduser("~/.reel-room/zernio.json")
        try:
            with open(cfg, encoding="utf-8") as f:
                acc = json.load(f).get("instagramAccountId")
        except (OSError, ValueError):
            acc = None
    return acc


def list_accounts():
    r = call("GET", "/accounts")
    items = r.get("data", r.get("accounts", r)) if isinstance(r, dict) else r
    return items if isinstance(items, list) else []


def pick_instagram(accounts):
    ig = [a for a in accounts if str(a.get("platform", "")).lower() == "instagram"]
    return (ig[0].get("_id") or ig[0].get("id") or ig[0].get("accountId")) if len(ig) == 1 else None


# ---------------------------------------------------------------- inputs
def probe_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def to_jpeg(path):
    """Instagram covers must be JPEG. Convert next to the original (keeps the original untouched)."""
    if path.lower().endswith((".jpg", ".jpeg")):
        return path
    out = os.path.splitext(path)[0] + ".jpg"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-q:v", "2", "-frames:v", "1", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(f"could not convert the cover to JPEG: {r.stderr.strip()[-200:]}", "install ffmpeg (doctor.py) or pass a .jpg cover")
    return out


def from_project(project, a):
    renders = os.path.join(project, "renders")
    shares = sorted(glob.glob(os.path.join(renders, "*-share.mp4")), key=os.path.getmtime)
    if not shares:
        die(f"no *-share.mp4 in {renders}", "run deliver.py first")
    video = shares[-1]
    stem = video[: -len("-share.mp4")]
    cover = next((c for c in (stem + "-cover.jpg", stem + "-cover.png") if os.path.exists(c)), None)
    cap = os.path.join(project, "caption.txt")
    return video, cover, cap if os.path.exists(cap) else None


def read_caption(a, project_caption):
    if a.caption is not None:
        return a.caption.strip()
    path = a.caption_file or project_caption
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        die(f"cannot read caption file: {e}")


def build(a):
    problems, warnings = [], []
    video = cover = None
    media = []
    project_caption = None
    if a.project:
        project = os.path.abspath(a.project)
        if not os.path.isdir(project):
            die(f"project folder not found: {project}")
        if not a.video and not a.image:
            video, cover, project_caption = from_project(project, a)
    if a.video:
        for v in a.video:
            media.append(("video", os.path.abspath(v)))
    elif video:
        media.append(("video", video))
    for im in a.image or []:
        media.append(("image", os.path.abspath(im)))
    cover = os.path.abspath(a.cover) if a.cover else cover
    if not media:
        die("nothing to post", "give --video, --image, or --project")
    for kind, p in media:
        if not os.path.isfile(p):
            die(f"file not found: {p}")
    if a.carousel or len(media) > 1:
        if len(media) < 2:
            die("a carousel needs at least 2 files")
        if len(media) > MAX_CAROUSEL:
            die(f"a carousel holds at most {MAX_CAROUSEL} files, you gave {len(media)}")
        carousel = True
    else:
        carousel = False
    if carousel and a.trial:
        die("trial reels cannot be carousels", "drop --trial or post a single video")
    if not carousel and media[0][0] != "video":
        die("a single post must be a video (use --carousel for images)")
    if not carousel:
        size = os.path.getsize(media[0][1])
        if size > IG_MAX_VIDEO_BYTES:
            problems.append(f"video is {size / 1e6:.0f} MB, Instagram allows 300 MB")
        dur = probe_duration(media[0][1])
        if dur and dur > IG_MAX_REEL_S:
            problems.append(f"reel is {dur:.0f}s, Instagram reels allow {IG_MAX_REEL_S}s")
        if cover is not None and not os.path.isfile(cover):
            die(f"cover not found: {cover}")
        if cover is None:
            warnings.append("no cover given: Instagram will use a frame of its own choosing")
    caption = read_caption(a, project_caption)
    if not caption:
        warnings.append("caption is empty")
    if len(caption) > IG_MAX_CAPTION:
        problems.append(f"caption is {len(caption)} characters, Instagram allows {IG_MAX_CAPTION}")
    if len(re.findall(r"#\w+", caption)) > IG_MAX_HASHTAGS:
        problems.append(f"more than {IG_MAX_HASHTAGS} hashtags, Instagram rejects that")
    if a.mode == "schedule" and not (a.at and a.tz):
        die("schedule needs --at and --tz", "example: --at 2026-10-12T12:00:00 --tz America/New_York")
    if a.mode == "schedule" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", a.at):
        die(f"--at '{a.at}' is not a local ISO time", "use YYYY-MM-DDTHH:MM:SS, for example 2026-10-12T12:00:00")
    return {"media": media, "cover": cover, "caption": caption, "carousel": carousel,
            "problems": problems, "warnings": warnings}


def payload(a, plan, urls, account_id):
    items = [{"type": kind, "url": urls[p]} for kind, p in plan["media"]]
    psd = {}
    if not plan["carousel"]:
        psd["shareToFeed"] = not a.no_feed
        if plan["cover"]:
            psd["instagramThumbnail"] = urls[plan["cover_upload"]]
        if a.trial:
            psd["trialParams"] = {"graduationStrategy": a.graduation}
    body = {"content": plan["caption"], "mediaItems": items,
            "platforms": [{"platform": "instagram", "accountId": account_id, "platformSpecificData": psd}]}
    if a.mode == "now":
        body["publishNow"] = True
    elif a.mode == "schedule":
        body["scheduledFor"] = a.at
        body["timezone"] = a.tz
    return body


def manual_steps(plan, a):
    names = ", ".join(os.path.basename(p) for _, p in plan["media"])
    steps = [f"1. Send {names}" + (f" and {os.path.basename(plan['cover'])}" if plan["cover"] else "") + " to your phone (AirDrop, iCloud or Drive).",
             "2. Instagram > + > Reel > pick the video." if not plan["carousel"] else "2. Instagram > + > Post > select all the files in order.",
             ]
    if not plan["carousel"]:
        steps.append("3. Tap Cover > Add from camera roll > pick the cover image.")
        steps.append("4. Turn on 'Trial' (Try it first) so it goes to non-followers first." if a.trial else "4. Leave 'Trial' off to post to followers.")
    steps.append("5. Paste the caption (it is in your caption file) and tap Share.")
    return steps


def main():
    ap = argparse.ArgumentParser(description="Reel Room post (Zernio)", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Zernio affiliate link: " + AFFILIATE)
    ap.add_argument("--project", help="project folder: uses the newest renders/*-share.mp4, its cover and caption.txt")
    ap.add_argument("--video", nargs="+", help="video file(s)")
    ap.add_argument("--image", nargs="+", help="image file(s) (carousel)")
    ap.add_argument("--carousel", action="store_true", help="post several files as one carousel")
    ap.add_argument("--cover", help="cover image (PNG or JPEG)")
    ap.add_argument("--caption", help="caption text")
    ap.add_argument("--caption-file", help="file holding the caption")
    ap.add_argument("--account-id", help="Instagram account id in Zernio")
    ap.add_argument("--mode", choices=["draft", "now", "schedule"], default="draft")
    ap.add_argument("--at", help="schedule time, local ISO, e.g. 2026-10-12T12:00:00")
    ap.add_argument("--tz", help="schedule timezone, e.g. America/New_York")
    ap.add_argument("--trial", action="store_true", help="Instagram trial reel")
    ap.add_argument("--graduation", choices=["MANUAL", "SS_PERFORMANCE"], default="MANUAL",
                    help="trial: MANUAL (you graduate it in the app) or SS_PERFORMANCE (auto)")
    ap.add_argument("--no-feed", action="store_true", help="reel only, do not also show in the feed grid")
    ap.add_argument("--dry-run", action="store_true", help="build the payload only: no network, no uploads")
    ap.add_argument("--list-accounts", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    have_key = bool(os.environ.get(KEY_ENV))
    if a.list_accounts:
        if not have_key:
            die(f"{KEY_ENV} is not set", f"get Zernio here: {AFFILIATE}", 3)
        print(json.dumps(list_accounts(), indent=2))
        return
    plan = build(a)
    if plan["problems"]:
        die("; ".join(plan["problems"]), "fix those and run again")
    if plan["cover"]:
        # dry-run never writes anything: just name the JPEG that a real run would upload
        plan["cover_upload"] = (os.path.splitext(plan["cover"])[0] + ".jpg") if a.dry_run else to_jpeg(plan["cover"])

    if not have_key and not a.dry_run:
        print("Zernio is not set up (no ZERNIO_API_KEY). Post it by hand, or get Zernio to post for you:")
        print(f"  {AFFILIATE}\n")
        print("\n".join(manual_steps(plan, a)))
        sys.exit(3)

    uploads = [p for _, p in plan["media"]] + ([plan["cover_upload"]] if plan["cover"] else [])
    if a.dry_run:
        urls = {p: "https://dry-run.invalid/uploads/" + os.path.basename(p) for p in uploads}
        account = instagram_account(a.account_id) or "<instagram-account-id>"
    else:
        account = instagram_account(a.account_id) or pick_instagram(list_accounts())
        if not account:
            die("no Instagram account chosen", "pass --account-id, set ZERNIO_INSTAGRAM_ACCOUNT_ID, or run --list-accounts")
        urls = {}
        for p in uploads:
            print(f"uploading {os.path.basename(p)} ({os.path.getsize(p) / 1e6:.1f} MB)", file=sys.stderr, flush=True)
            urls[p] = upload(p)
    body = payload(a, plan, urls, account)
    result = {"dry_run": a.dry_run, "mode": a.mode, "trial": a.trial, "carousel": plan["carousel"],
              "uploads": [{"file": p, "size": os.path.getsize(p) if os.path.exists(p) else None} for p in uploads],
              "warnings": plan["warnings"], "payload": body}
    if not a.dry_run:
        result["response"] = call("POST", "/posts", body)
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for w in plan["warnings"]:
            print(f"warning: {w}")
        print(("DRY RUN, nothing was uploaded or posted.\n" if a.dry_run else "Posted to Zernio.\n") +
              f"mode {a.mode}{' (trial reel, ' + a.graduation + ')' if a.trial else ''}{', carousel' if plan['carousel'] else ''}")
        print(json.dumps(result["response"] if not a.dry_run else body, indent=2)[:3000])


if __name__ == "__main__":
    main()
