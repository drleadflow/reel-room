"""Condensed cut for the carousel slide-up style: re-cut chosen takes from the FULL-RES source with a reframe that
puts the face high (so the card stack fits under the chin), exact frame counts, voice joins with 20 ms fade-in /
30 ms fade-out in measured silence, optional silent tail from the source and a per-piece punch-in.

style_cfg.cut = {
  "source": "/abs/IMG_6545.MOV", "offset": 5.0,        # source time = segment src time + offset
  "from_project": "/abs/sample",                         # project whose segments.json / words.json the pieces refer to
  "crop": {"w": 1548, "h": 2752, "x": 346, "y": 995},    # 9:16 window in source pixels, scaled to 1080x1920
  "grade": {...},                                        # behind.grade_lut args
  "pieces": [{"seg": "hook"}, {"seg": "n1b", "to": 16.80, "punch": 1.06}, {"seg": "n2", "tail": 18}]
}                                                        # to = cut time in from_project (must be in silence)
Writes assets/aroll.mp4 (graded, AAC), assets/voice.wav (untouched pcm), words.json, segments.json (new cut times).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stylekit"))
import kit  # noqa: E402

FPS = 30


def build(proj, log=print):
    cfg = proj.style["cut"]
    key = hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:10]
    stamp = proj.p("work", "cut.key")
    if os.path.exists(stamp) and open(stamp).read() == key and os.path.exists(proj.p("assets", "aroll.mp4")):
        return
    src_proj = cfg["from_project"]
    segs = {s["id"]: s for s in kit.jload(os.path.join(src_proj, "segments.json"))}
    words = kit.jload(os.path.join(src_proj, "words.json"))
    c = cfg["crop"]
    work = proj.p("work", "cut")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    lst, new_words, new_segs, frame = [], [], [], 0
    for i, pc in enumerate(cfg["pieces"]):
        s = segs[pc["seg"]]
        a0 = s["frame"] / FPS
        a1 = pc.get("to", (s["frame"] + s["frames"]) / FPS)
        n = int(round((a1 - a0) * FPS)) + int(pc.get("tail", 0))
        t_src = s["src_in"] + cfg["offset"]
        z = float(pc.get("punch", 1.0))
        cw, ch = int(round(c["w"] / z / 2) * 2), int(round(c["h"] / z / 2) * 2)
        cx, cy = c["x"] + (c["w"] - cw) * 0.5, c["y"] + (c["h"] - ch) * float(c.get("punch_anchor_y", 0.3))
        dur = n / FPS
        out = os.path.join(work, f"p{i}.mkv")
        vf = f"crop={cw}:{ch}:{int(cx)}:{int(cy)},scale=1080:1920:flags=lanczos,setsar=1,fps={FPS}"
        af = (f"atrim=0:{dur:.5f},asetpts=PTS-STARTPTS,aresample=48000,afade=t=in:d=0.02,"
              f"afade=t=out:st={max(0, dur - 0.03):.5f}:d=0.03,apad=whole_dur={dur:.5f}")
        kit.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t_src:.5f}", "-i", cfg["source"], "-frames:v", str(n),
                 "-vf", vf, "-af", af, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-preset", "slow", "-crf", "10",
                 "-pix_fmt", "yuv420p", "-c:a", "pcm_s24le", "-ar", "48000", "-ac", "2", out])
        got = kit.probe(out)["frames"]
        if got != n:
            raise SystemExit(f"piece {pc['seg']}: {got} frames, wanted {n}")
        lst.append(out)
        off = frame / FPS - a0
        for w in words:
            if a0 - 1e-6 <= float(w["start"]) < a1 - 0.02:
                new_words.append({"text": w["text"], "start": round(float(w["start"]) + off, 3),
                                  "end": round(min(float(w["end"]), a1) + off, 3)})
        new_segs.append({"id": pc["seg"], "frame": frame, "frames": n, "src_in": round(t_src, 4), "punch": z,
                         "from": [round(a0, 4), round(a1, 4)]})
        log(f"  piece {pc['seg']}: source {t_src:.3f}s, {n} frames (punch {z})")
        frame += n
    joined = os.path.join(work, "joined.mkv")
    ins = [x for p in lst for x in ("-i", p)]
    fc = "".join(f"[{k}:v][{k}:a]" for k in range(len(lst))) + f"concat=n={len(lst)}:v=1:a=1[v][a]"
    kit.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-fps_mode", "passthrough",
             "-c:v", "libx264", "-preset", "slow", "-crf", "10", "-pix_fmt", "yuv420p", "-c:a", "pcm_s24le", joined])
    got = kit.probe(joined)["frames"]
    if got != frame:
        raise SystemExit(f"joined cut has {got} frames, wanted {frame}")
    kit.run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-vn", "-c:a", "pcm_s24le", proj.p("assets", "voice.wav")])
    tmp = os.path.join(work, "joined_aac.mp4")
    kit.run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", tmp])
    import behind
    behind.build_base(tmp, proj.p("assets", "aroll.mp4"), grade=cfg.get("grade"), log=log)
    got = kit.probe(proj.p("assets", "aroll.mp4"))["frames"]
    if got != frame:
        raise SystemExit(f"condensed cut has {got} frames, wanted {frame}")
    kit.jsave(proj.p("words.json"), new_words)
    kit.jsave(proj.p("segments.json"), new_segs)
    with open(stamp, "w") as fh:
        fh.write(key)
    import skface as facetrack
    res = facetrack.track(proj.p("assets", "aroll.mp4"), 3)
    kit.jsave(proj.p("work", "facetrack.json"), res)
    log(f"condensed cut: {frame} frames ({frame / FPS:.2f} s), {len(new_words)} words, face track {len(res['boxes'])} samples")
