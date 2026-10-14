"""Showcase reels ("On real reels" in the Room's Styles tab): review copies, posters and the db doc.

Usage:
  showcase.py copy <master.mp4> <out.mp4> [--poster-from IMG | --poster-at SEC] [--max-mb 12] [--json]
      720x1280 H.264 + AAC 128k, faststart, under --max-mb (2 tries, the second at a lower bitrate).
      Writes <out>.jpg next to it (720 wide): from --poster-from (an existing poster image), else a frame at
      --poster-at (default 25% of the length).
  showcase.py check <catalog.json> [--max-mb 12] [--json]
      Every example's src/poster exists, src is under --max-mb, has audio, is 720 wide, and is faststart.
  showcase.py doc <catalog.json> <assets.json> [--json]
      Prints the `styles/examples` db doc: {items:[{style, style_label?, reel, title, person, src, poster,
      preview_kind:"video", seconds, kind}]}. <assets.json> maps the catalog's local paths ("styles/showcase/x.mp4")
      to the asset urls the Artifact upload returned. Items whose src or poster has no asset url are left out
      (listed in "missing").

Catalog shape (styles/catalog.json, version 2): each style may carry `examples: [{title, person, reel, src, poster,
seconds, kind:"showcase"}]`; top-level `examples_offcatalog` holds reels in a look the catalog does not have
(each with `style_label`). Paths are relative to the skill folder (SK).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SK = Path(__file__).resolve().parent.parent
AUDIO_KBPS = 128
MAX_VIDEO_KBPS = 2200
SIZE_MARGIN = 0.93  # aim under the cap: container overhead + rate-control drift


def video_kbps(dur: float, max_mb: float, factor: float = 1.0) -> int:
    """bitrate that lands the file under max_mb (MiB) with AUDIO_KBPS of audio"""
    if dur <= 0:
        raise ValueError("duration must be positive")
    total = max_mb * 8 * 1024 * SIZE_MARGIN / dur
    return max(250, min(MAX_VIDEO_KBPS, int((total - AUDIO_KBPS) * factor)))


def encode(src, dst, kbps: int):
    C.ffmpeg(["-i", src, "-vf", "scale=720:1280:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
              "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k", "-bufsize", f"{kbps * 2}k",
              "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ac", "2", "-movflags", "+faststart", dst])


def make_poster(dst_jpg, image=None, video=None, at=None):
    if image:
        C.ffmpeg(["-i", image, "-vf", "scale=720:-2", "-q:v", "3", dst_jpg])
    else:
        C.ffmpeg(["-ss", f"{at:.3f}", "-i", video, "-frames:v", "1", "-vf", "scale=720:-2", "-q:v", "3", dst_jpg])


def review_copy(src, dst, max_mb=12.0, poster_from=None, poster_at=None) -> dict:
    info = C.probe(src)
    if not info["has_audio"]:
        raise RuntimeError(f"{src} has no audio track (the showcase copy keeps the master's mix)")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    for factor in (1.0, 0.82):
        kbps = video_kbps(info["dur"], max_mb, factor)
        encode(src, dst, kbps)
        if dst.stat().st_size <= max_mb * 1024 * 1024:
            break
    else:
        raise RuntimeError(f"{dst.name} is still over {max_mb} MB at {kbps} kbps")
    poster = dst.with_suffix(".jpg")
    make_poster(poster, image=poster_from, video=src, at=poster_at if poster_at is not None else info["dur"] * 0.25)
    return {"src": str(dst), "poster": str(poster), "seconds": round(info["dur"], 1), "kbps": kbps,
            "mb": round(dst.stat().st_size / 1048576, 2)}


def iter_examples(catalog: dict):
    """yield (style_id_or_None, example) for every example in a version 2 catalog"""
    for s in catalog.get("styles", []):
        for ex in s.get("examples", []) or []:
            yield s["id"], ex
    for ex in catalog.get("examples_offcatalog", []) or []:
        yield None, ex


def is_faststart(path) -> bool:
    """moov atom before mdat (the page can start playing before the whole file arrives)"""
    with open(path, "rb") as f:
        head = f.read(1 << 20)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    return moov != -1 and (mdat == -1 or moov < mdat)


def check_example(ex: dict, max_mb: float) -> list:
    problems = []
    src, poster = SK / ex.get("src", ""), SK / ex.get("poster", "")
    for key in ("title", "person", "reel", "src", "poster", "seconds", "kind"):
        if key not in ex:
            problems.append(f"missing {key}")
    if not src.is_file():
        return problems + [f"src not found: {ex.get('src')}"]
    if not poster.is_file():
        problems.append(f"poster not found: {ex.get('poster')}")
    mb = src.stat().st_size / 1048576
    if mb > max_mb:
        problems.append(f"{mb:.1f} MB is over {max_mb} MB")
    info = C.probe(src)
    if info["w"] != 720:
        problems.append(f"width {info['w']}, want 720")
    if not info["has_audio"]:
        problems.append("no audio")
    if not is_faststart(src):
        problems.append("not faststart")
    return problems


def check(catalog: dict, max_mb=12.0) -> dict:
    rows = []
    for style, ex in iter_examples(catalog):
        rows.append({"style": style, "src": ex.get("src"), "problems": check_example(ex, max_mb)})
    return {"ok": all(not r["problems"] for r in rows), "count": len(rows), "rows": rows}


def examples_doc(catalog: dict, assets: dict) -> dict:
    """the `styles/examples` db doc, local paths swapped for asset urls"""
    items, missing = [], []
    for style, ex in iter_examples(catalog):
        src, poster = assets.get(ex.get("src")), assets.get(ex.get("poster"))
        if not src or not poster:
            missing.append(ex.get("src"))
            continue
        item = {"style": style, "reel": ex.get("reel"), "title": ex.get("title"), "person": ex.get("person"),
                "src": src, "poster": poster, "preview_kind": "video", "seconds": ex.get("seconds"),
                "kind": ex.get("kind", "showcase")}
        if style is None:
            item["style_label"] = ex.get("style_label") or "Other look"
        items.append(item)
    return {"items": items, "missing": missing}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["copy", "check", "doc"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--poster-from")
    ap.add_argument("--poster-at", type=float)
    ap.add_argument("--max-mb", type=float, default=12.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "copy":
            if len(a.args) != 2:
                C.fail("copy needs <master.mp4> <out.mp4>", "showcase.py copy in.mp4 SK/styles/showcase/x.mp4")
            res = review_copy(a.args[0], a.args[1], a.max_mb, a.poster_from, a.poster_at)
        elif a.cmd == "check":
            res = check(C.read_json(a.args[0]), a.max_mb)
        else:
            if len(a.args) != 2:
                C.fail("doc needs <catalog.json> <assets.json>", "assets.json = {\"styles/showcase/x.mp4\": \"/_blob/..\"}")
            res = examples_doc(C.read_json(a.args[0]), C.read_json(a.args[1]))
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        C.fail(str(e), "Check the paths and that ffmpeg is installed (doctor.py).")
    if a.json or a.cmd == "doc":
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif a.cmd == "check":
        for r in res["rows"]:
            print(("OK   " if not r["problems"] else "FAIL ") + f"{r['style'] or 'off-catalog'}  {r['src']}  "
                  + "; ".join(r["problems"]))
        print(f"{'PASS' if res['ok'] else 'FAIL'}: {res['count']} examples")
    else:
        print(f"{res['src']}  {res['mb']} MB  {res['seconds']} s  {res['kbps']} kbps  poster {res['poster']}")
    return 0 if (a.cmd != "check" or res["ok"]) else 1


if __name__ == "__main__":
    sys.exit(main())
