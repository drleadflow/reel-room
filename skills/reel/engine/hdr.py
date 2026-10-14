#!/usr/bin/env python3
"""hdr.py: make every video a composition uses SDR bt709 with a keyframe every 30 frames.

  python hdr.py <project> [--json]          check + fix every video index.html uses (and assets/aroll.mp4)
  python hdr.py <file> [<file> ...]         check + fix these files in place

Why: iPhone footage is tagged HLG (bt2020 / arib-std-b67). HyperFrames 0.8.34 then treats the whole composition as
HDR, and on its frame-extraction pass it runs every other video through a bt709 -> bt2020 colorspace filter that
DROPS THE ALPHA PLANE. A cut-out of the speaker (VP9 with alpha) is then pasted as an opaque frame of the room over
every layer under it. Lint, check and snapshot all pass (they decode in live Chrome); only the real render breaks.
`--sdr` does not prevent it.

Fix (lossless when the keyframes are already dense): retag the H.264 stream as bt709 (h264_metadata bitstream filter
+ container tags). Chrome already tone-maps the clip that way in previews, so the look does not change. A file with
sparse keyframes (> 30 frames apart, e.g. a phone b-roll) is re-encoded at CRF 14 with `-g 30` (the renderer warns
about "seek failures and frame freezing" on sparse keyframes). A VP9/alpha file tagged HDR is re-encoded with alpha.

Every fix is logged to <project>/work/hdr_fix.json (QA `hdr_alpha` reads it).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HDR_TRC = {"arib-std-b67", "smpte2084"}
HDR_PRIM = {"bt2020"}
HDR_MATRIX = {"bt2020nc", "bt2020c"}
GOP_MAX = 30
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def _run(cmd, timeout=1800):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{os.path.basename(cmd[0])} failed: {(p.stderr or '')[-400:]}")
    return p.stdout


def probe(path):
    """{codec, pix_fmt, trc, primaries, matrix, alpha, hdr, frames?} of the first video stream."""
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=codec_name,pix_fmt,color_transfer,color_primaries,color_space:stream_tags=alpha_mode",
                "-of", "json", path])
    s = (json.loads(out).get("streams") or [{}])[0]
    tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
    info = {"codec": s.get("codec_name"), "pix_fmt": s.get("pix_fmt"), "trc": s.get("color_transfer"),
            "primaries": s.get("color_primaries"), "matrix": s.get("color_space"),
            "alpha": str(tags.get("alpha_mode", "0")) == "1" or "yuva" in str(s.get("pix_fmt"))}
    info["hdr"] = (info["trc"] in HDR_TRC) or (info["primaries"] in HDR_PRIM) or (info["matrix"] in HDR_MATRIX)
    return info


def max_gop(path, limit_s=None):
    """Largest distance between keyframes in frames (30 fps assumed for the frame count)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey", "-show_entries",
           "frame=pts_time,best_effort_timestamp_time", "-of", "csv=p=0"]
    if limit_s:
        cmd += ["-read_intervals", f"%+{limit_s}"]
    out = _run(cmd + [path], timeout=600)
    ts = []
    for line in out.splitlines():
        for part in line.split(","):
            try:
                ts.append(float(part))
                break
            except ValueError:
                continue
    ts = sorted(set(ts))
    if len(ts) < 2:
        return 9999 if ts else 0
    return int(round(max(b - a for a, b in zip(ts, ts[1:])) * 30))


def _retag_h264(path, tmp):
    _run(["ffmpeg", "-v", "error", "-y", "-i", path, "-map", "0", "-c", "copy",
          "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
          "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
          "-movflags", "+faststart", tmp])


def _reencode(path, tmp, info):
    tags = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    if info["codec"] == "vp9" or path.lower().endswith(".webm"):
        pix = "yuva420p" if info["alpha"] else "yuv420p"
        _run(["ffmpeg", "-v", "error", "-y", "-c:v", "libvpx-vp9", "-i", path, "-map", "0:v:0", "-c:v", "libvpx-vp9",
              "-pix_fmt", pix, "-b:v", "0", "-crf", "18", "-g", str(GOP_MAX), "-row-mt", "1", "-deadline", "good",
              "-cpu-used", "4", "-auto-alt-ref", "0", *tags, "-metadata:s:v:0", f"alpha_mode={1 if info['alpha'] else 0}",
              tmp])
        return
    _run(["ffmpeg", "-v", "error", "-y", "-i", path, "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
          "-preset", "medium", "-crf", "14", "-g", str(GOP_MAX), "-keyint_min", str(GOP_MAX), "-bf", "0",
          "-x264-params", "scenecut=0", "-pix_fmt", "yuv420p", *tags, "-c:a", "copy", "-movflags", "+faststart", tmp])


def fix_file(path, check_gop=True):
    """Fix one file in place. Returns a log row {file, before, action, after} (action 'none' when already fine)."""
    info = probe(path)
    gop = max_gop(path) if check_gop and info["codec"] in ("h264", "hevc", "vp9") else 0
    row = {"file": path, "before": {k: info[k] for k in ("codec", "trc", "primaries", "matrix", "alpha")}, "gop": gop}
    sparse = gop > GOP_MAX
    if not info["hdr"] and not sparse:
        row["action"] = "none"
        return row
    ext = os.path.splitext(path)[1] or ".mp4"
    fd, tmp = tempfile.mkstemp(suffix=ext, dir=os.path.dirname(path))
    os.close(fd)
    try:
        if info["codec"] == "h264" and not sparse:
            _retag_h264(path, tmp)
            row["action"] = "retag bt709 (lossless)"
        else:
            _reencode(path, tmp, info)
            row["action"] = f"re-encode bt709 GOP {GOP_MAX}" + (" with alpha" if info["alpha"] else "")
            if info["hdr"] and info["codec"] != "h264":
                row["warning"] = ("HDR source re-encoded without tone mapping (this ffmpeg has no zscale): colours may look "
                                  "flat. Prefer assets cut through assemble.py, which outputs H.264 that only needs a retag.")
        after = probe(tmp)
        if after["hdr"]:
            raise RuntimeError(f"{path} still reads as HDR after the fix")
        if info["alpha"] and not after["alpha"]:
            raise RuntimeError(f"{path} lost its alpha plane in the fix")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        row["after"] = {k: after[k] for k in ("codec", "trc", "primaries", "matrix", "alpha")}
        return row
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def composition_videos(project, index="index.html"):
    """Every local video the composition loads (src="..." on <video>), plus assets/aroll.mp4."""
    out = []
    p = os.path.join(project, index)
    if os.path.exists(p):
        html = open(p, encoding="utf-8").read()
        for m in re.finditer(r'<video[^>]*\ssrc="([^"]+)"', html):
            rel = m.group(1)
            if "://" in rel:
                continue
            from urllib.parse import unquote
            full = os.path.normpath(os.path.join(project, unquote(rel)))
            if not full.startswith(os.path.abspath(project) + os.sep):
                continue      # never rewrite a file outside the project folder
            if full.lower().endswith(VIDEO_EXT) and os.path.exists(full) and full not in out:
                out.append(full)
    aroll = os.path.join(project, "assets", "aroll.mp4")
    if os.path.exists(aroll) and aroll not in out:
        out.insert(0, aroll)
    return out


def _sig(path):
    st = os.stat(path)
    return f"{st.st_size}:{int(st.st_mtime)}"


def fix_project(project, index="index.html", log=print):
    """Check every video of the composition; fix what is HDR-tagged or sparse. Cached by file size + mtime."""
    project = os.path.abspath(project)
    logp = os.path.join(project, "work", "hdr_fix.json")
    try:
        state = json.load(open(logp))
    except (OSError, ValueError):
        state = {"files": {}}
    rows = []
    for f in composition_videos(project, index):
        rel = os.path.relpath(f, project)
        prev = state["files"].get(rel)
        if prev and prev.get("sig") == _sig(f):
            rows.append(prev)
            continue
        row = fix_file(f)
        row["file"] = rel
        row["sig"] = _sig(f)
        if row["action"] != "none":
            log(f"  hdr: {rel}: {row['action']} (was {row['before']['trc']}/{row['before']['primaries']}, GOP {row['gop']})")
            if prev and prev.get("action") not in (None, "none"):
                row["history"] = prev.get("history", []) + [prev["action"]]
        elif prev and prev.get("action") not in (None, "none"):
            row["action"], row["history"] = "none (fixed earlier)", prev.get("history", []) + [prev["action"]]
        state["files"][rel] = row
        rows.append(row)
    os.makedirs(os.path.dirname(logp), exist_ok=True)
    with open(logp, "w") as fh:
        json.dump(state, fh, indent=1)
    return rows


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    if len(args) == 1 and os.path.isdir(args[0]):
        rows = fix_project(args[0])
    else:
        rows = [fix_file(os.path.abspath(a)) for a in args]
    if "--json" in argv:
        print(json.dumps({"ok": True, "files": rows}, indent=1))
    else:
        for r in rows:
            print(f"{r['file']}: {r['action']}")


if __name__ == "__main__":
    main(sys.argv[1:])
