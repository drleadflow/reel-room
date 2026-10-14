"""aroll_fix.py: find and remove the repeated frames that assemble's seek + fps step can add to assets/aroll.mp4.

Usage: aroll_fix.py <project> [--check] [--json]
  (no flag)  measure, then rebuild the picture when assemble added repeats (the aroll's audio is kept untouched)
  --check    only measure; exit 1 when assemble added repeats

Why: assemble cuts each segment with `-ss <in> -i src ... fps=30`. After the input seek the timestamps can sit off the
1/30 grid and the fps step then repeats a frame: the first frame of a segment (a hitch on every cut), or every third
frame on some sources (the segment plays at about 20 fps). Seen on the showcase showcase reels and a test short.

Detection: mean absolute difference of neighbouring frames at 90x160 gray, a repeat is under REPEAT_DIFF. The same
window of the SOURCE is measured too and only repeats the source does not have count ("added"), so a still or a
frozen intro in the source is never called a stutter. ffmpeg mpdecimate over the aroll is reported as a cross-check
(it cannot tell source stills from added repeats).

Fix: every segment is re-cut with assemble's crop, zoom and grade but WITHOUT the fps step: seek half a frame before
the in point, take exactly `frames` frames, `-fps_mode passthrough`, raw H.264 joined byte for byte and stamped at
30 fps, then the aroll's own audio is copied back. The new file replaces aroll.mp4 only when the frame count matches
segments.json and it has fewer added repeats. Sources outside 29.9..30.1 fps need the fps step and are not re-cut.

Wired in: assemble.py runs `auto()` after it writes the aroll (project.json "aroll_fix": "off" turns it off) and
qa.py runs `check()` as the `aroll_repeats` gate.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

FPS = C.FPS
REPEAT_DIFF = 0.15          # mean abs gray diff (0..255) under which two neighbouring frames are the same picture
SMALL = (90, 160)
FIXABLE_FPS = (29.9, 30.1)


def gray_diffs(path, ss=None, frames=None):
    """neighbour-frame differences (len = frames - 1) of a video, or of `frames` frames from `ss` seconds"""
    import numpy as np
    w, h = SMALL
    cmd = [C.ffmpeg_bin(), "-v", "error", "-nostdin"] + (["-ss", f"{ss:.4f}"] if ss is not None else []) + ["-i", str(path)]
    cmd += (["-frames:v", str(frames)] if frames else []) + ["-an", "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8)
    if f.size < w * h * 2:
        return np.zeros(0)
    f = f[: f.size // (w * h) * (w * h)].reshape(-1, h, w).astype(np.int16)
    return np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))


def added_repeats(cut_d, src_d, thr=REPEAT_DIFF):
    """indexes (inside the segment) where the cut repeats a frame but the source window does not"""
    out = []
    for j, d in enumerate(cut_d):
        src_still = j < len(src_d) and src_d[j] < thr
        if d < thr and not src_still:
            out.append(j)
    return out


def mpdecimate_drops(path) -> int:
    r = subprocess.run([C.ffmpeg_bin(), "-hide_banner", "-nostdin", "-i", str(path), "-an", "-vf", "scale=270:480,mpdecimate",
                        "-loglevel", "debug", "-f", "null", "-"], capture_output=True, text=True)
    return len(re.findall(r"\bdrop pts", r.stderr))


def measure(proj) -> dict:
    proj = Path(proj)
    segs = C.read_json(proj / "segments.json")
    srcs = C.source_info(proj)
    aroll = gray_diffs(proj / "assets" / "aroll.mp4")
    whole = {}          # each source decoded once, start to end: a seek would add the same repeat we look for
    rows, total = [], 0
    for s in segs:
        n = int(s["frames"])
        cut_d = aroll[s["frame"]: s["frame"] + n - 1]
        if s["clip"] not in whole:
            whole[s["clip"]] = gray_diffs(srcs[s["clip"]]["path"])
        f0 = int(round(s["src_in"] * float(srcs[s["clip"]].get("fps") or FPS)))
        src_d = whole[s["clip"]][f0: f0 + n - 1]
        add = added_repeats(cut_d, src_d)
        total += len(add)
        rows.append({"id": s["id"], "frames": n, "added": len(add), "at": [s["frame"] + 1 + j for j in add][:12]})
    return {"total_added": total, "segments": rows, "frames": len(aroll) + 1 if len(aroll) else 0}


def summary(m: dict) -> str:
    bad = [r for r in m["segments"] if r["added"]]
    if not bad:
        return f"no repeated frames added by the cut ({m['frames']} frames checked against the source)"
    worst = sorted(bad, key=lambda r: -r["added"])[:4]
    return (f"{m['total_added']} repeated frames in {len(bad)} segments: "
            + ", ".join(f"{r['id']} {r['added']}/{r['frames']} (frame {r['at'][0]})" for r in worst))


def check(project) -> dict:
    """qa.py gate: {name, pass, detail, label}; skipped when there is no aroll or segments.json"""
    p = Path(project)
    base = {"name": "aroll_repeats", "label": "Your footage plays smoothly (no repeated frames from the cut)"}
    need = [p / "assets" / "aroll.mp4", p / "segments.json", p / "sources.json"]
    if not all(f.exists() for f in need):
        return {**base, "pass": True, "skipped": True, "detail": "no assets/aroll.mp4, segments.json or sources.json"}
    missing = [si["path"] for si in C.source_info(p).values() if not Path(si["path"]).exists()]
    if missing:
        return {**base, "pass": True, "skipped": True, "detail": f"source clip not found ({missing[0]}), cannot compare"}
    try:
        m = measure(p)
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        return {**base, "pass": False, "detail": f"could not measure repeated frames: {e}"}
    fix = "" if not m["total_added"] else f". Fix: aroll_fix.py {p} (or re-run assemble.py, it fixes this itself)"
    return {**base, "pass": m["total_added"] == 0, "detail": summary(m) + fix}


def recut_segment(s, src, info, vf_extra, crf, dest):
    """one segment, assemble's framing, no fps step -> raw H.264 at dest"""
    from assemble import OUT_W, OUT_H, crop_box
    cw, ch, x, y = crop_box(info["w"], info["h"], s.get("zoom", 1.0), s.get("cx", 0.5), s.get("cy", 0.5))
    vf = f"crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos" + (f",{vf_extra}" if vf_extra else "")
    vf += ",setsar=1,format=yuv420p"
    C.ffmpeg(["-nostdin", "-ss", f"{max(0.0, s['src_in'] - 0.5 / FPS):.4f}", "-i", src, "-an", "-sn", "-dn", "-vf", vf,
              "-frames:v", s["frames"], "-fps_mode", "passthrough", "-c:v", "libx264", "-preset", "medium", "-crf", crf,
              "-g", FPS, "-bf", 0, "-x264-params", "scenecut=0", "-f", "h264", dest])


def frame_count(path) -> int:
    r = C.run([C.ffprobe_bin(), "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
               "stream=nb_read_packets", "-of", "csv=p=0", path])
    return int((r.stdout.strip() or "0").split(",")[0])


def fixable_clips(srcs) -> set:
    ok = set()
    for clip, si in srcs.items():
        fps = si.get("fps") or C.probe(si["path"])["fps"]
        if FIXABLE_FPS[0] <= float(fps) <= FIXABLE_FPS[1]:
            ok.add(clip)
    return ok


def rebuild(proj, crf=14) -> Path:
    """re-cut every segment without the fps step -> work/aroll_fixed.mp4 (aroll audio copied). Returns the path."""
    proj = Path(proj)
    segs = C.read_json(proj / "segments.json")
    srcs = C.source_info(proj)
    infos = {c: {**si, **{k: v for k, v in C.probe(si["path"]).items() if k in ("w", "h")}} for c, si in srcs.items()}
    pj = C.read_json(proj / "project.json", default={}) if (proj / "project.json").exists() else {}
    vf_extra = (pj.get("grade") or {}).get("filter", "") or ""
    work = proj / "work" / "aroll_fix"
    work.mkdir(parents=True, exist_ok=True)
    joined = work / "video.h264"
    with open(joined, "wb") as fo:
        for s in segs:
            part = work / f"{s['id']}.h264"
            recut_segment(s, infos[s["clip"]]["path"], infos[s["clip"]], vf_extra, crf, part)
            with open(part, "rb") as fi:
                shutil.copyfileobj(fi, fo)
            part.unlink()
    out = work / "aroll_fixed.mp4"
    C.ffmpeg(["-nostdin", "-framerate", FPS, "-f", "h264", "-i", joined, "-i", proj / "assets" / "aroll.mp4", "-map", "0:v:0",
              "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", out])
    joined.unlink()
    want = sum(int(s["frames"]) for s in segs)
    got = frame_count(out)
    if got != want:
        out.unlink()
        raise RuntimeError(f"the rebuilt picture has {got} frames, segments.json says {want}; aroll.mp4 left unchanged")
    return out


def fix(proj, crf=14, before=None) -> dict:
    """measure, rebuild when needed, swap in only when it is better. Returns {action, before, after}"""
    proj = Path(proj)
    before = before or measure(proj)
    if not before["total_added"]:
        return {"action": "none", "before": before["total_added"], "after": before["total_added"]}
    bad = {r["id"] for r in before["segments"] if r["added"]}
    clips = {s["clip"] for s in C.read_json(proj / "segments.json") if s["id"] in bad}
    if not clips <= fixable_clips(C.source_info(proj)):
        return {"action": "skipped", "before": before["total_added"], "after": before["total_added"],
                "why": "a source is not 30 fps, so the fps step is needed there"}
    fixed = rebuild(proj, crf)
    aroll = proj / "assets" / "aroll.mp4"
    keep = aroll.with_suffix(".prefix.mp4")
    aroll.replace(keep)
    fixed.replace(aroll)
    after = measure(proj)
    if after["total_added"] >= before["total_added"]:
        keep.replace(aroll)          # not better: put the original back
        return {"action": "reverted", "before": before["total_added"], "after": after["total_added"]}
    keep.unlink()
    try:                              # same SDR retag assemble does (iPhone HLG/PQ tags break cut-out alpha)
        import hdr
        hdr.fix_file(str(aroll))
    except Exception as e:  # noqa: BLE001  never lose the fix over a tag; render prep retries
        print(f"WARNING: could not retag aroll.mp4 as SDR ({e})", file=sys.stderr)
    return {"action": "fixed", "before": before["total_added"], "after": after["total_added"],
            "detail": summary(after)}


def auto(proj, log=print, crf=14) -> dict:
    """assemble hook: never raises, logs one line"""
    try:
        res = fix(proj, crf)
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        log(f"WARNING: repeated-frame check failed ({e}). Run: aroll_fix.py {proj}")
        return {"action": "failed", "error": str(e)}
    if res["action"] != "none":
        log(f"repeated frames: {res['before']} added by the cut -> {res['after']} ({res['action']})")
    return res


def main():
    ap = argparse.ArgumentParser(description="Find and fix repeated frames in assets/aroll.mp4")
    ap.add_argument("project")
    ap.add_argument("--check", action="store_true", help="measure only; exit 1 when the cut added repeats")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    proj = C.need_project(a.project, ["segments.json", "sources.json", "assets/aroll.mp4"], a.json)
    try:
        m = measure(proj)
        res = {"check": m} if a.check else fix(proj, before=m)
    except (RuntimeError, OSError, KeyError) as e:
        C.fail(str(e), "Run assemble.py first; check the source paths in sources.json.", a.json)
    if not a.check:
        res["mpdecimate_drops"] = mpdecimate_drops(proj / "assets" / "aroll.mp4")
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(summary(m) if a.check else f"{res['action']}: added repeats {res['before']} -> {res['after']}, "
              f"mpdecimate drops now {res['mpdecimate_drops']} (includes stills that are in the source)")
    sys.exit(1 if a.check and m["total_added"] else 0)


if __name__ == "__main__":
    main()
