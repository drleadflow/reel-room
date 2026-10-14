#!/usr/bin/env python3
"""gallery.py <project> <out_dir> [--no-render] [--sfx] [--bed] [--loop-at 12.0] [--poster-at 14.5] [--workers N]

Style demo deliverables from one project (any style that the split engine composes):
  1. compose + lint (0 errors) + render with HyperFrames 0.8.34 (screenshot capture: no 1-frame overlay lag)
  2. audio: the A-roll voice mastered to -14 LUFS (one linear gain + true-peak guard), optional synthesized SFX on the
     graphic entrances (>= 18 dB under the voice) and an optional quiet lo-fi bed (>= 20 dB under), see sound.py
  3. <out>/demo.mp4 (1080x1920, 30 fps, exact frame count, H.264 ~10 Mbps, < 45 MB), <out>/demo-voiceonly.mp4 when SFX/bed are on,
     <out>/loop.mp4 (6 s, silent, < 4 MB), <out>/poster.jpg
  4. styleqa.py -> <out>/qa/report.json + contact sheets
Settings may also live in project.json "gallery": {"sfx": bool, "bed": bool, "loop_at": s, "poster_at": s, "plan": {...}}
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render as rnd  # noqa: E402
import sound  # noqa: E402

LOOP_MAX = 4_000_000
DEMO_MAX = 45_000_000


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"failed: {' '.join(cmd[:6])}...\n{p.stderr[-800:]}")
    return p.stdout


def frames_of(path):
    out = sh(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
              "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", path])
    s = json.loads(out)["streams"][0]
    return int(s["nb_read_frames"]), s["width"], s["height"], s["r_frame_rate"]


def render_video(project, rel, workers=None):
    """workers: cap HyperFrames' parallel Chrome workers (shared machine); None = the CLI's auto."""
    t = time.time()
    os.makedirs(os.path.join(project, "renders"), exist_ok=True)
    rnd.prep_media(project)
    cmd = rnd.HF + ["render", "-o", rel, "--quality", "high", "--sdr", "--experimental-fast-capture=false"]
    if workers:
        cmd += ["-w", str(int(workers))]
    env = dict(os.environ, PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS="180000", PRODUCER_PLAYER_READY_TIMEOUT_MS="180000")
    p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, env=env)
    with open(os.path.join(project, "renders", ".render.log"), "w") as f:
        f.write(p.stdout + p.stderr)
    if p.returncode or not os.path.exists(os.path.join(project, rel)):
        raise SystemExit("render failed:\n" + (p.stdout + p.stderr)[-1500:])
    print(f"  rendered {rel} in {time.time() - t:.0f}s")


def make_loop(src, out, at, dur=6.0):
    for crf in (20, 23, 26, 29):
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", src, "-t", f"{dur:.3f}", "-an", "-c:v", "libx264",
            "-preset", "slow", "-crf", str(crf), "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out])
        if os.path.getsize(out) < LOOP_MAX:
            return crf
    raise SystemExit("loop.mp4 does not fit under 4 MB")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    project, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    os.makedirs(os.path.join(out, "qa"), exist_ok=True)
    pj = json.load(open(os.path.join(project, "project.json")))
    g = pj.get("gallery", {})
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    use_sfx = "--sfx" in argv or g.get("sfx", False)
    use_bed = "--bed" in argv or g.get("bed", False)
    loop_at = float(opt("--loop-at", g.get("loop_at", 0.0)))
    poster_at = float(opt("--poster-at", g.get("poster_at", 1.0)))
    slug = pj.get("slug", "reel")
    rel = f"renders/{slug}-gallery.mp4"
    raw = os.path.join(project, rel)
    if "--no-render" not in argv:
        import compose
        rep = compose.compose(project)
        for w in rep["warnings"]:
            print("  WARN", w)
        errs, warns, outp = rnd.lint(project)
        print(f"  lint: {errs} error(s), {warns} warning(s)")
        if errs:
            print(rnd.short_findings(outp, "error"))
            raise SystemExit("lint errors")
        render_video(project, rel, opt("--workers"))
    lb = json.load(open(os.path.join(project, "layout_boxes.json")))
    if lb.get("list"):  # list plan for the engine's list check: number glyph boxes, reveal times, clear time
        with open(os.path.join(out, "list.json"), "w") as f:
            json.dump(lb["list"], f, indent=1)
    n, w, h, fr = frames_of(raw)
    print(f"  raw render: {n} frames {w}x{h} @ {fr} (want {lb['frames']})")

    # audio
    wav = os.path.join(project, "work", "gallery_mix.wav")
    arep = sound.build(project, wav, use_sfx, use_bed, g.get("plan", {}))
    dur = lb["frames"] / 30.0

    def mux(audio, dst):
        """H.264 high at ~10 Mbps (crisp type, under 45 MB for a 35 s reel); steps down until it fits."""
        for mb in (10, 8.5, 7):
            sh(["ffmpeg", "-v", "error", "-y", "-i", raw, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p", "-b:v", f"{mb}M",
                "-maxrate", f"{mb * 1.4:.1f}M", "-bufsize", f"{mb * 2:.0f}M", "-r", "30",
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{dur:.4f}", "-movflags", "+faststart", dst])
            if os.path.getsize(dst) < DEMO_MAX:
                return
        raise SystemExit(f"{dst} does not fit under 45 MB")

    demo = os.path.join(out, "demo.mp4")
    mux(wav, demo)
    lufs, tp, _ = sound.loudness(demo)
    arep["demo"] = {"lufs": lufs, "tp": tp}
    if use_sfx or use_bed or (arep.get("motion_sfx") or {}).get("placed"):
        vwav = os.path.join(project, "work", "gallery_voice.wav")
        arep["voiceonly"] = sound.build(project, vwav, False, False, motion=False)["mix"]
        mux(vwav, os.path.join(out, "demo-voiceonly.mp4"))
    with open(os.path.join(out, "qa", "audio.json"), "w") as f:
        json.dump(arep, f, indent=1)
    print(f"  demo.mp4: {lufs:.1f} LUFS, TP {tp:.1f} dBTP; sfx {len(arep.get('sfx') or [])}; bed {arep.get('bed')}")

    crf = make_loop(demo, os.path.join(out, "loop.mp4"), loop_at)
    print(f"  loop.mp4 at {loop_at}s crf {crf}: {os.path.getsize(os.path.join(out, 'loop.mp4')) / 1e6:.2f} MB")
    sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{poster_at:.3f}", "-i", demo, "-frames:v", "1", "-q:v", "2",
        os.path.join(out, "poster.jpg")])
    import styleqa
    ok = styleqa.run(project, demo, out)
    print(f"  QA {'PASS' if ok else 'FAIL'}: {os.path.join(out, 'qa', 'report.json')}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) else 1)
