"""Cached set bake: assets/base.mp4 built from one video chunk per cut, each cached on disk.

  bake_cached(project, workers=3)    assets/base.mp4 + work/bake_qa.json (same files as bake.bake)

  room cut  the A-roll frames re-encoded with the bake's encoder settings; key = A-roll content hash + frame span,
            so a room chunk is made once per A-roll and reused by every plan
  set cut   bake.bake(span) for that cut; key = A-roll hash + span + the cut's look (set colours, headline layers,
            punch-in, set / headline / edge config, cut-out masks, bake code). A new plan re-bakes only the set
            cuts that changed.
Chunks start on a keyframe and share one encoder setting, so they join with a stream copy (+ the A-roll audio).
Shared-machine limits: at most `workers` processes, each x264 encode (veryfast, crf 11) on 2 threads, OpenCV on 2 threads, nice'd by the
caller. Cache: <project>/work/bake_cache/<aroll hash>/. Turned on by "editorial": {"bake": {"cache": true}}.
"""
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import plan as _plan
import kit  # noqa: F401  (stylekit, on sys.path through plan)

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = ("bake.py", "bake_fast.py", "layers.py", "etheme.py", "plan.py", "bake_cache.py")
X264 = ["-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "11", "-g", "30", "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def _sha(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _code_hash() -> str:
    h = hashlib.sha1()
    for f in CODE:
        h.update(open(os.path.join(HERE, f), "rb").read())
    return h.hexdigest()[:12]


def aroll_key(pl) -> str:
    import sys
    sys.path.append(os.path.join(os.path.dirname(os.path.dirname(HERE)), "engine"))
    import common as C
    return C.content_hash(pl.proj.p("assets", "aroll.mp4"))[:16]


def set_key(pl, s, hl_specs, code) -> str:
    """Everything that changes a set cut's pixels."""
    import etheme as theme
    tok = theme.tokens(pl.proj.brand, pl.cfg)
    keys = {s["set"]} | {h["set"] for h in pl.headlines if h["seg"] == s["id"]}
    look = {k: theme.scheme(tok, pl.cfg, k) for k in sorted(keys)}
    geo = {k: s[k] for k in ("f0", "f1", "scene", "set", "zoom", "anchor", "brow", "chin", "head_top")}
    cfg = {k: pl.cfg.get(k) for k in ("set", "headline", "matte", "palette")}
    return _sha({"geo": geo, "look": look, "cfg": cfg, "hl": hl_specs.get(s["id"], []), "code": code})


def jobs_for(pl, cdir, code):
    """[(kind, f0, f1, chunk path, qa path or None)] for every cut, in order (cached ones included)."""
    import bake
    import etheme as theme
    specs = {}
    for h in bake.Headlines(pl, theme.tokens(pl.proj.brand, pl.cfg)).items:     # renders the layers once (cached)
        specs.setdefault(h["seg"], []).append({"f0": h["f0"], "f1": h["f1"], "spec": h["render"]["spec"]})
    out = []
    for s in pl.segs:
        if s["scene"] == "room":
            name = f"room-{s['f0']:05d}-{s['f1']:05d}-{code}"
            out.append(("room", s["f0"], s["f1"], os.path.join(cdir, name + ".mp4"), None))
        else:
            name = f"{s['scene']}-{s['f0']:05d}-{set_key(pl, s, specs, code)}"
            out.append(("set", s["f0"], s["f1"], os.path.join(cdir, name + ".mp4"), os.path.join(cdir, name + ".json")))
    return out


def _room(project, f0, f1, out):
    """The A-roll's frames [f0, f1) re-encoded like a baked chunk (keyframe first, same x264 settings)."""
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(project, "assets", "aroll.mp4"), "-an", "-vf",
                    f"select=between(n\\,{f0}\\,{f1 - 1}),setpts=N/FRAME_RATE/TB", "-r", "30"] + X264 + [tmp],
                   check=True)
    os.replace(tmp, out)


def _one(job):
    import cv2
    cv2.setNumThreads(2)
    project, kind, f0, f1, out, qa = job
    if kind == "room":
        _room(project, f0, f1, out)
    else:
        import bake
        bake.bake(project, log=lambda *_: None, span=(f0, f1), out_path=out, qa_path=qa)
    return out


def _join(pl, chunks, out):
    lst = out + ".list.txt"
    with open(lst, "w") as f:
        f.writelines(f"file '{c}'\n" for c in chunks)
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i",
                    pl.proj.p("assets", "aroll.mp4"), "-map", "0:v", "-map", "1:a", "-c", "copy", "-movflags",
                    "+faststart", tmp], check=True)
    os.remove(lst)
    got = kit.probe(tmp)["frames"]
    if got != pl.frames:
        raise SystemExit(f"cached bake joined {got} frames, expected {pl.frames}")
    os.replace(tmp, out)


def _qa(jobs):
    import bake_par
    return bake_par._merge_qa([q for kind, _a, _b, _c, q in jobs if kind == "set" and q and os.path.exists(q)])


def bake_cached(project, log=print, workers=3):
    pl = _plan.Plan(project)
    code = _code_hash()
    cdir = pl.proj.p("work", "bake_cache", aroll_key(pl))
    os.makedirs(cdir, exist_ok=True)
    jobs = jobs_for(pl, cdir, code)
    todo = [(pl.dir, *j) for j in jobs if not os.path.exists(j[3])]
    log(f"bake: {len(jobs)} cuts, {len(jobs) - len(todo)} cached, {len(todo)} to make "
        f"({sum(1 for j in todo if j[1] == 'set')} set) on {workers} processes")
    if todo:
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine"))
        RL = __import__("rrlimits")             # engine-wide CPU budget: pool size and the ffmpeg share per process
        workers = RL.pool_workers(workers, per_worker=2)
        RL.share(workers)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_one, sorted(todo, key=lambda j: j[1] != "set")))      # set cuts first (the long ones)
    _join(pl, [j[3] for j in jobs], pl.proj.p("assets", "base.mp4"))
    qa = _qa(jobs)
    kit.jsave(pl.proj.p("work", "bake_qa.json"), qa)
    log(f"bake: {pl.frames} frames, matte {qa['sources']}, max headline leak {qa['max_leak_px']} px")
    return qa
