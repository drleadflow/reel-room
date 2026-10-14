#!/usr/bin/env python3
"""make.py <project> --out <dir> [--no-render] [--qa-only]

editorial-ui end to end (same steps as stylekit/build.py, plus the set-specific QA):
  1. compose.py: bake the set layer (cached) + index.html + work/meta.json
  2. hyperframes 0.8.34 lint (0 errors) + render -> renders/raw.mp4
  3. sound: voice untouched + synthesized UI SFX (>= 18 LU under the voice) -> <out>/demo.mp4 (-14 LUFS, TP <= -1.5,
     ~9.5 Mbps) and <out>/demo-voiceonly.mp4 (no SFX)
  4. <out>/loop.mp4 (6 s, silent, < 4 MB), <out>/poster.jpg
  5. stylekit/skqa.py checks -> <out>/qa/report.json, switches.jpg, overview.jpg, face.jpg; <project>/layout_boxes.json
     (measured boxes + speaker face) and <out>/demo-master.mp4 links for engine/qa.py
  6. set checks -> <out>/qa/set_report.json: every set frame matted by BiRefNet (no fallback), headline never visible
     over the face (bake_qa leak), plus <out>/qa/contact.jpg (one frame per beat) and <out>/qa/matte_edges.jpg
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan as _plan  # noqa: E402
import kit  # noqa: E402
import skqa  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("eui_compose", os.path.join(HERE, "compose.py"))
compose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compose)

FPS = 30
_grab = kit.grab


def _grab_chunked(video, frames, scale=360):
    """kit.grab builds one ffmpeg select expression; past ~100 frames ffmpeg rejects it and returns nothing.
    Same result, fetched in chunks of 60 (patched in for this process only)."""
    fr = sorted(set(frames))
    out = {}
    for i in range(0, len(fr), 60):
        out.update(_grab(video, fr[i:i + 60], scale))
    return out


kit.grab = _grab_chunked


def contact(pl, demo, out):
    """One labelled frame shortly after every beat: each cut, each headline and each card entrance."""
    marks = []
    for s in pl.segs:
        marks.append((min(s["f0"] + 4, s["f1"] - 1), f"{s['id']} {s['scene']}{' ' + s['set'] if s['scene'] == 'set' else ''}"))
    for h in pl.headlines:
        marks.append((min(h["f0"] + 12, h["f1"] - 1), f"{h['text'].replace('|', ' ').replace('_', '')} ({h['set']})"))
    for c in pl.cards:
        marks.append((min(c["f0"] + 12, c["f1"] - 1), f"{c['kind']}"))
        if c.get("done_f"):
            marks.append((min(c["done_f"] + 10, c["f1"] - 1), "done chip"))
    marks = sorted({m[0]: m for m in marks}.values())
    imgs = kit.grab(demo, [m[0] for m in marks], scale=300)
    kit.label_sheet([imgs[m[0]] for m in marks], [f"{m[0] / FPS:.2f}s {m[1]}"[:34] for m in marks], out, cols=8)


def matte_edges(pl, demo, out):
    """Close-ups of the cut-out edge (cap, ears, shoulders, hands) on set frames, 2x."""
    import numpy as np
    set_frames = [f for s in pl.segs if s["scene"] == "set" for f in range(s["f0"] + 2, s["f1"] - 1, 9)]
    raw = kit.grab(demo, set_frames, scale=1080)
    tiles, labels = [], []
    for f in set_frames[:: max(1, len(set_frames) // 12)][:12]:
        im = raw[f]
        b = pl.head_box(f)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        x0, y0 = int(max(0, min(1080 - 420, cx - 210))), int(max(0, min(1920 - 420, cy - 260)))
        tiles.append(np.ascontiguousarray(im[y0:y0 + 420, x0:x0 + 420]))
        labels.append(f"f{f} head")
        y1 = int(min(1920 - 420, cy + 330))
        tiles.append(np.ascontiguousarray(im[y1:y1 + 420, 0:420]))
        labels.append(f"f{f} left arm")
    kit.label_sheet(tiles, labels, out, cols=6)


def set_checks(pl, qa_dir):
    bq = kit.jload(pl.proj.p("work", "bake_qa.json"), {})
    src = bq.get("sources", {})
    res = [{"name": "matte_source", "pass": src.get("fallback", 1) == 0,
            "detail": f"BiRefNet frames {src.get('birefnet')}, cut-out cache frames {src.get('cutout', 0)}, "
                      f"fallback (u2net webm) frames {src.get('fallback')}"},
           {"name": "headline_behind_face", "pass": bq.get("max_leak_px", 1) == 0 and bq.get("max_core_holes", 1) <= 25,
            "detail": f"every 3rd set frame: headline pixels showing through the face {bq.get('max_leak_px')}, "
                      f"see-through holes inside the silhouette over the face (max) {bq.get('max_core_holes')}"}]
    for r in res:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['name']}: {r['detail']}")
    kit.jsave(os.path.join(qa_dir, "set_report.json"), {"pass": all(r["pass"] for r in res), "checks": res,
                                                       "plan": pl.summary()})
    return all(r["pass"] for r in res)


def link_master(demo):
    """demo.mp4 already comes out of deliver.make_master (-14 LUFS, TP <= -1.5). Expose it as <stem>-master.mp4 (hard
    link, same bytes) so engine/qa.py checks it as is. Re-mastering it would cut one more AAC frame off the audio and
    `-shortest` would then drop the last video frame (1042 of 1043)."""
    master = os.path.splitext(demo)[0] + "-master.mp4"
    if os.path.exists(master):
        os.remove(master)
    os.link(demo, master)


def _keys(boxes):
    """(id, text, kind, n): n tells apart same-looking boxes shown at once (id-less cards)."""
    seen, out = {}, []
    for b in boxes:
        k = (b["id"], b["text"], b["kind"])
        seen[k] = seen.get(k, -1) + 1
        out.append(k + (seen[k],))
    return out


def _settled_runs(samples, step, jump=40):
    """[[(frame, [x, y, w, h], op, readable)]]: settled box samples (within 2 px of their neighbouring samples, the
    skqa safe-zone rule), split into runs where a box disappears for a sample or lands somewhere else (> jump px)."""
    keyed = [list(zip(_keys(s["boxes"]), s["boxes"])) for s in samples]
    pos = [{k: [b["x"], b["y"], b["w"], b["h"]] for k, b in kb} for kb in keyed]
    runs, open_ = [], {}
    for si, s in enumerate(samples):
        for key, b in keyed[si]:
            r = [b["x"], b["y"], b["w"], b["h"]]
            nb = [pos[j][key] for j in (si - 1, si + 1) if 0 <= j < len(pos) and key in pos[j]]
            if b["kind"] == "cutaway" or b["op"] <= 0.5 or any(max(abs(p - q) for p, q in zip(o, r)) > 2 for o in nb):
                continue
            run = open_.get(key)
            if not run or s["f"] - run[-1][0] > step or max(abs(p - q) for p, q in zip(run[0][1], r)) > jump:
                run = open_[key] = []
                runs.append((key, run))
            run.append((s["f"], r, b["op"], b["readable"]))
    return runs


def write_layout_boxes(project, meta, step=3):
    """layout_boxes.json for engine/qa.py, measured from the composed page (not the spec): every readable box as the
    union of its settled on-screen rects while it is shown (op > 0.5), captions on their exact caption frames, and the
    speaker face (tracked face through the motion camera, skqa padding) for every sampled frame without a full cutaway."""
    proj = kit.Project(project)
    samples = kit.sample(proj.p("index.html"), meta["frames"], step=step)
    boxes = []
    for (bid, text, kind, _n), rows in _settled_runs(samples, step):
        x0 = min(r[1][0] for r in rows); y0 = min(r[1][1] for r in rows)  # noqa: E702
        x1 = max(r[1][0] + r[1][2] for r in rows); y1 = max(r[1][1] + r[1][3] for r in rows)  # noqa: E702
        b = {"kind": kind, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "text": text, "readable": rows[0][3],
             "t0": round(rows[0][0] / FPS, 3), "t1": round((rows[-1][0] + step) / FPS, 3)}
        if kind == "caption":
            cap = next((c for c in meta.get("caption_list", []) if c["text"] == text and c["f0"] <= rows[0][0] <= c["f1"]), None)
            if cap:
                b["t0"], b["t1"] = round(cap["f0"] / FPS, 3), round(cap["f1"] / FPS, 3)
            b["style"] = "pill"
        boxes.append(b)
    ft, mplan, speaker = kit.jload(proj.p(meta["facetrack"])), kit.M.load_plan(proj.dir) or {}, []
    for s in samples:
        if any(b["kind"] == "cutaway" and b["op"] > 0.9 and b["w"] * b["h"] > 0.9 * 1080 * 1920 for b in s["boxes"]):
            continue
        fb = skqa.cam_face(skqa.face_at(ft, s["f"]), mplan, s["f"])
        if fb:
            speaker.append({"t0": round(s["f"] / FPS, 3), "t1": round((s["f"] + step) / FPS, 3),
                            "face": {"cx": round(fb[0] + fb[2] / 2), "cy": round(fb[1] + fb[3] / 2),
                                     "w": round(fb[2]), "h": round(fb[3])}})
    kit.jsave(os.path.join(project, "layout_boxes.json"), {"style": meta["template"], "frames": meta["frames"],
                                                           "boxes": boxes, "speaker": speaker})
    return len(boxes), len(speaker)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args or "--out" not in argv:
        raise SystemExit(__doc__)
    project = os.path.abspath(args[0])
    out = os.path.abspath(argv[argv.index("--out") + 1])
    qa_dir = os.path.join(out, "qa")
    os.makedirs(qa_dir, exist_ok=True)
    demo = os.path.join(out, "demo.mp4")
    t = time.time()
    if "--qa-only" not in argv:
        meta = compose.compose(project, bake_layer="--no-bake" not in argv)
        errs, warns, findings = kit.lint(project)
        print(f"lint: {errs} error(s), {warns} warning(s)")
        if errs:
            print(findings)
            raise SystemExit("lint errors; fix before rendering")
        raw = os.path.join(project, "renders", "raw.mp4")
        if "--no-render" not in argv or not os.path.exists(raw):
            print(f"render: {kit.render(project, 'renders/raw.mp4'):.0f}s")
        voice = os.path.join(project, meta["voice_src"])
        dry = kit.mix_and_master(project, raw, voice, [], os.path.join(out, "demo-voiceonly.mp4"), meta["frames"],
                                 motion_sfx=False)
        mix = kit.mix_and_master(project, raw, voice, meta["cues"], demo, meta["frames"])
        meta["mix"], meta["mix_voiceonly"] = mix, dry
        kit.jsave(os.path.join(project, "work", "meta.json"), meta)
        print(f"master: {mix['master']}, sfx margin {mix['sfx_margin_lu']} LU, {len(meta['cues'])} cues")
        link_master(demo)
        link_master(os.path.join(out, "demo-voiceonly.mp4"))   # qa's gap audit measures pauses on the voice-only master
        print(f"loop: {kit.make_loop(demo, os.path.join(out, 'loop.mp4'), meta['loop']['t0'], meta['loop'].get('dur', 6.0))}")
        kit.make_poster(demo, os.path.join(out, "poster.jpg"), meta["poster"]["t"])
        shutil.copyfile(os.path.join(project, "index.html"), os.path.join(qa_dir, "index.html"))
    pl = _plan.Plan(project)
    res = skqa.run(project, demo, qa_dir)
    print("layout_boxes.json: %d boxes, %d speaker samples" % write_layout_boxes(project, kit.jload(os.path.join(project, "work", "meta.json"))))
    ok = set_checks(pl, qa_dir)
    contact(pl, demo, os.path.join(qa_dir, "contact.jpg"))
    matte_edges(pl, demo, os.path.join(qa_dir, "matte_edges.jpg"))
    print(f"done in {time.time() - t:.0f}s -> {out}  ({'PASS' if res['pass'] and ok else 'FAIL'})")
    sys.exit(0 if res["pass"] and ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
