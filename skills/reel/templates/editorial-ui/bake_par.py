"""Parallel bake: the same set layer as bake.py, cut into spans baked by N processes, then joined.

  bake_parallel(project, workers=6)    assets/base.mp4 + work/bake_qa.json (same files as bake.bake)

Each span reads one frame of context on each side, so the matte's temporal smoothing is the same as in a single bake
(headlines and plates are functions of the frame number); takeover cuts are never split; each span starts on a
keyframe, so the chunks join with a stream copy. Spans are balanced by cost (a set frame costs ~12 room frames). Turned on by project.json
"editorial": {"bake": {"workers": N}} (the plan compiler sets it); one process when N <= 1.
"""
import json
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor

import plan as _plan
import kit  # noqa: F401  (stylekit, on sys.path through plan)

SET_COST, ROOM_COST = 1.0, 0.08


def _cost(s):
    return (s["f1"] - s["f0"]) * (SET_COST if s["scene"] in ("set", "takeover") else ROOM_COST)


def spans(pl, n):
    """Contiguous (f0, f1) spans of about equal cost, n of them. A set cut may be split (bake reads one frame of
    context on each side, so the temporal matte is unchanged); a takeover cut never is (one webm per cut)."""
    cost = []
    for s in pl.segs:
        c = SET_COST if s["scene"] in ("set", "takeover") else ROOM_COST
        cost += [(f, c, s["scene"] == "takeover" and f != s["f0"]) for f in range(s["f0"], s["f1"])]
    want = sum(c for _, c, _ in cost) / max(1, n)
    out, start, acc = [], 0, 0.0
    for f, c, glued in cost:
        if acc >= want and not glued and len(out) < n - 1:
            out.append((start, f))
            start, acc = f, 0.0
        acc += c
    out.append((start, pl.frames))
    return out


def _init():
    """Two OpenCV threads per bake process (and 3 x264 threads per span): N processes x all-core pools thrash."""
    import cv2
    cv2.setNumThreads(2)


def _one(job):
    import bake
    project, f0, f1, out, qa = job
    cc = bake.cutout_cache(_plan.Plan(project))
    if cc and cc[0].waiting():          # pipeline.py: the cut-out is still running; bake this span once its masks exist
        pl = _plan.Plan(project)
        cc[0].wait_for(project, [f for s in pl.segs if s["scene"] in ("set", "takeover")
                                 for f in range(max(s["f0"], f0 - 1), min(s["f1"], f1 + 1))])
    bake.bake(project, log=lambda *_: None, span=(f0, f1), out_path=out, qa_path=qa)
    return out, qa


def _merge_qa(parts):
    qa = {"frames": {}, "max_leak_px": 0, "max_core_holes": 0, "sources": {}, "cutouts": {}, "warnings": [],
          "headlines": [], "seconds": 0.0}
    for p in parts:
        d = json.load(open(p))
        qa["frames"].update(d.get("frames", {}))
        qa["max_leak_px"] = max(qa["max_leak_px"], d.get("max_leak_px", 0))
        qa["max_core_holes"] = max(qa["max_core_holes"], d.get("max_core_holes", 0))
        for k, v in d.get("sources", {}).items():
            qa["sources"][k] = qa["sources"].get(k, 0) + v
        qa["cutouts"].update(d.get("cutouts", {}))
        qa["seconds"] = max(qa["seconds"], d.get("seconds", 0))
        seen = {h["id"] for h in qa["headlines"]}
        qa["headlines"] += [h for h in d.get("headlines", []) if h["id"] not in seen]
        qa["warnings"] = d.get("warnings", qa["warnings"])
    return qa


def _join(pl, chunks, out):
    lst = pl.proj.p("work", "bake_chunks", "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{c}'\n" for c in chunks)
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i",
                    pl.proj.p("assets", "aroll.mp4"), "-map", "0:v", "-map", "1:a", "-c", "copy", "-movflags",
                    "+faststart", tmp], check=True)
    got = kit.probe(tmp)["frames"]
    if got != pl.frames:
        raise SystemExit(f"parallel bake joined {got} frames, expected {pl.frames}")
    os.replace(tmp, out)


def bake_parallel(project, log=print, workers=6):
    import bake
    import etheme as theme
    pl = _plan.Plan(project)
    if workers <= 1:
        return bake.bake(project, log=log)
    bake.Headlines(pl, theme.tokens(pl.proj.brand, pl.cfg))      # render the headline layers once (disk cache)
    d = pl.proj.p("work", "bake_chunks")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    jobs = [(pl.dir, a, b, os.path.join(d, f"c{i:02d}.mp4"), os.path.join(d, f"c{i:02d}.json"))
            for i, (a, b) in enumerate(spans(pl, workers))]
    log(f"bake: {len(jobs)} spans on {workers} processes")
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        done = list(ex.map(_one, jobs))
    _join(pl, [c for c, _ in done], pl.proj.p("assets", "base.mp4"))
    qa = _merge_qa([q for _, q in done])
    kit.jsave(pl.proj.p("work", "bake_qa.json"), qa)
    shutil.rmtree(d, ignore_errors=True)
    log(f"bake: {pl.frames} frames, matte {qa['sources']}, max headline leak {qa['max_leak_px']} px")
    return qa
