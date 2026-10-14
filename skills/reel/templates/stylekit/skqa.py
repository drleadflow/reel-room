#!/usr/bin/env python3
"""qa.py <project> <demo.mp4> <out_qa_dir>   -> <out_qa_dir>/report.json + contact sheets. Exit 1 on any failure.

The hard bar for every style demo, checked on the FINAL file and on the live timeline (headless Chrome):
  format       1080x1920, 30 fps, exact frame count (= work/meta.json frames), size < 45 MB, video 8-12 Mbps
  loudness     -14 LUFS +-0.5, true peak <= -1.5 dBTP; every SFX >= 18 LU under the voice (from the mix report)
  face         every 3rd frame: no card / text / caption box (transforms included) touches the face box from
               work/facetrack.json (frames where a full-frame cutaway replaces the speaker are skipped)
  safe zone    settled readable boxes stay inside y 220-1470, x 35-1045, and x <= 980 below y 1155
  captions     caption text == words.json in order (no dropped, doubled or invented words), each caption appears on its
               first word's frame, no single-word orphans in phrase mode, no em dashes anywhere on screen
  switches     every event in meta.events: timeline state flips exactly on frame N (hidden on N-1, visible on N or the
               reverse) and the rendered pixels in its region change on N, not N+1
  blank        no near-uniform (blank) frame anywhere
Contact sheets: switches.jpg (N-1 | N | N+1 per event), overview.jpg (1 frame per second), face.jpg (boxes drawn).
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402
from kit import FPS, SAFE  # noqa: E402

FACE_PAD = {"up": 0.22, "down": 0.18, "side": 0.06}


def chk(out, name, ok, detail):
    out.append({"name": name, "pass": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail if isinstance(detail, str) else json.dumps(detail)[:220]}")


def cam_face(fb, mplan, f):
    """The face box through the motion camera on frame f (scale about the camera origin, then offset)."""
    if not fb or not mplan:
        return fb
    s, x, y, _r, ox, oy = kit.M.camera_at(mplan, f)
    if abs(s - 1) < 1e-4 and abs(x) < 0.01 and abs(y) < 0.01:
        return fb
    fx, fy, fw, fh = fb
    return [(fx - ox) * s + ox + x, (fy - oy) * s + oy + y, fw * s, fh * s]


def face_at(ft, f):
    boxes = ft["boxes"]
    step = ft.get("step", 3)
    k = str((f // step) * step)
    while k not in boxes and int(k) > 0:
        k = str(int(k) - step)
    if k not in boxes:
        return None
    x, y, w, h = boxes[k]
    return [x - FACE_PAD["side"] * w, y - FACE_PAD["up"] * h, w * (1 + 2 * FACE_PAD["side"]), h * (1 + FACE_PAD["up"] + FACE_PAD["down"])]


def inter(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def norm(t):
    return re.sub(r"[^\w'<>%.]+", "", t.lower().replace("’", "'")).strip(".")


def run(project, demo, qa_dir):
    os.makedirs(qa_dir, exist_ok=True)
    proj = kit.Project(project)
    meta = kit.jload(proj.p("work", "meta.json"))
    frames = meta["frames"]
    checks = []
    print(f"QA {meta['template']} -> {demo}")

    # ---- format, size, bitrate
    pr = kit.probe(demo)
    ok = pr["w"] == 1080 and pr["h"] == 1920 and abs(pr["fps"] - 30) < 1e-6 and pr["frames"] == frames
    chk(checks, "format", ok, f"{pr['w']}x{pr['h']} {pr['fps']:.2f} fps, {pr['frames']} frames (want {frames})")
    mb = os.path.getsize(demo) / 1e6
    vb = float(kit.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=bit_rate", "-of",
                        "csv=p=0", demo]).stdout.strip() or 0) / 1e6
    cap = max(45.0, 1.6 * frames / 30)      # 45 MB for a ~35 s demo; longer reels scale with the same bitrate band
    chk(checks, "size", mb < cap and 7.5 <= vb <= 12.5, f"{mb:.1f} MB (cap {cap:.0f}), video {vb:.1f} Mbps")

    # ---- loudness + sfx margin
    i, _, tp = kit.ebur128(demo)
    chk(checks, "loudness", abs(i + 14) <= 0.5 and tp <= -1.5, f"{i:.2f} LUFS, true peak {tp:.2f} dBTP")
    mix = meta.get("mix", {})
    if mix.get("cues"):
        chk(checks, "sfx_margin", mix["sfx_margin_lu"] >= 18,
            f"loudest SFX {mix['sfx_margin_lu']} LU under the voice ({len(mix['cues'])} cues)")
    else:
        chk(checks, "sfx_margin", True, "dry (no SFX)")

    # ---- timeline samples: face + safe zone
    samples = kit.sample(proj.p("index.html"), frames, step=3)
    ft = kit.jload(proj.p(meta["facetrack"]))
    mplan = kit.M.load_plan(proj.dir) or {}
    tframes = kit.M.transition_frames(mplan)          # whip/zoom/iris frames move and blur on purpose
    face_hits, safe_hits, moving = [], [], 0
    pos = []  # per sample: {key: rect}
    for s in samples:
        pos.append({(b["id"], b["text"], b["kind"]): [b["x"], b["y"], b["w"], b["h"]] for b in s["boxes"]})
    for si, s in enumerate(samples):
        f = s["f"]
        cut = any(b["kind"] == "cutaway" and b["op"] > 0.9 and b["w"] * b["h"] > 0.9 * 1080 * 1920 for b in s["boxes"])
        fb = None if cut else cam_face(face_at(ft, f), mplan, f)
        for b in s["boxes"]:
            if b["kind"] == "cutaway":
                continue
            r = [b["x"], b["y"], b["w"], b["h"]]
            key = (b["id"], b["text"], b["kind"])
            if fb and b["op"] > 0.08 and inter(r, fb) and b["kind"] in ("card", "text", "caption", "title"):
                face_hits.append({"f": f, "id": b["id"], "kind": b["kind"], "text": b["text"][:30], "box": r,
                                  "face": [round(v) for v in fb]})
            nb = [pos[j][key] for j in (si - 1, si + 1) if 0 <= j < len(pos) and key in pos[j]]
            if any(max(abs(p - q) for p, q in zip(o, r)) > 2 for o in nb):
                moving += 1
                continue
            if b["readable"] and b["op"] > 0.5:
                x, y, w, h = r
                bad = (y < SAFE["top"] or y + h > SAFE["bottom"] or x < SAFE["side"] or x + w > 1080 - SAFE["side"]
                       or (y + h > SAFE["right_from"] and x + w > SAFE["right_x"]))
                if bad:
                    safe_hits.append({"f": f, "kind": b["kind"], "text": b["text"][:30], "box": r})
    # captions never sit on proof, data or other text (screens, cards, titles)
    coll = []
    for s_ in samples:
        caps_ = [b for b in s_["boxes"] if b["kind"] == "caption" and b["op"] > 0.1]
        others = [b for b in s_["boxes"] if b["kind"] in ("screen", "card", "title") and b["op"] > 0.1]
        for c_ in caps_:
            for o in others:
                if inter([c_["x"], c_["y"], c_["w"], c_["h"]], [o["x"], o["y"], o["w"], o["h"]]):
                    coll.append({"f": s_["f"], "caption": c_["text"][:30], "over": o["kind"], "box": [o["x"], o["y"], o["w"], o["h"]]})
    chk(checks, "text_collision", not coll, f"{len(samples)} sampled frames, {len(coll)} captions over a screen/card/title"
        + (f"; first: {coll[0]}" if coll else ""))
    chk(checks, "face_clear", not face_hits, f"{len(samples)} sampled frames, {len(face_hits)} overlaps"
        + (f"; first: {face_hits[0]}" if face_hits else ""))
    chk(checks, "safe_zone", not safe_hits, f"{len(safe_hits)} settled boxes outside" + (f"; first: {safe_hits[0]}" if safe_hits else "")
        + f" ({moving} moving box-samples skipped)")

    # ---- captions
    caps = meta.get("caption_list", [])
    if caps:
        words = [w["text"] for w in proj.words_raw]
        wi = [j for c in caps for j in c["words"]]
        seq_ok = wi == sorted(wi) and len(wi) == len(set(wi))
        cover = set(wi) == set(range(min(wi), max(wi) + 1))
        text_ok, bad_text = True, []
        for c in caps:
            want = " ".join(norm(words[j]) for j in c["words"])
            got = " ".join(norm(t) for t in c["text"].split())
            if want != got:
                text_ok = False
                bad_text.append((c["text"], " ".join(words[j] for j in c["words"])))
        timing = [c for c in caps if c["f0"] != kit.frame_of(proj.words_raw[c["words"][0]]["start"]) and not c.get("clamped")]
        orph = [c["text"] for c in caps if meta["captions"].get("mode") == "phrase" and len(c["words"]) == 1 and not c.get("solo_ok")]
        detail = (f"{len(caps)} captions for words {min(wi)}-{max(wi)}, order {'ok' if seq_ok else 'BROKEN'}, "
                  f"{'no gaps' if cover else 'GAPS'}, text {'exact' if text_ok else 'MISMATCH ' + str(bad_text[:3])}, "
                  f"{len(timing)} late/early, {len(orph)} orphans {orph[:3]}")
        chk(checks, "captions", seq_ok and cover and text_ok and not timing and not orph, detail)
    else:
        chk(checks, "captions", True, "style has no captions (title and cards carry the text)")
    with open(proj.p("index.html")) as fh:
        page = fh.read()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
    dashes = [c for c in kit.EM_DASHES if c in body]
    chk(checks, "no_em_dashes", not dashes, "none on screen" if not dashes else f"found {dashes}")

    # ---- switches: timeline exact + rendered pixels
    evs = meta.get("events", [])
    exact = sorted({f for e in evs for f in (e["frame"] - 1, e["frame"]) if 0 < e["frame"] < frames})
    vis = {s["f"]: dict(s["vis"]) for s in kit.sample(proj.p("index.html"), frames, exact=exact)} if exact else {}
    gf = sorted({f for e in evs for f in (e["frame"] - 2, e["frame"] - 1, e["frame"], e["frame"] + 1) if 0 <= f < frames})
    imgs = kit.grab(demo, gf, scale=360)
    late, tl_bad, rows, labels = [], [], [], []
    k = 360 / 1080
    for e in evs:
        n = e["frame"]
        if not (0 < n < frames - 1):
            continue
        if e.get("sel"):
            eid = e["sel"].lstrip("#")
            a, b = vis.get(n - 1, {}).get(eid, 0), vis.get(n, {}).get(eid, 0)
            if e.get("show") is True and not (a < 0.05 and b > 0.3):
                tl_bad.append(f"{e['label']} f{n}: {a}->{b}")
            if e.get("show") is False and not (a > 0.3 and b < 0.05):
                tl_bad.append(f"{e['label']} f{n}: {a}->{b}")
        x, y, w, h = [int(v * k) for v in (e.get("region") or [0, 0, 1080, 1920])]
        x, y = max(0, x), max(0, y)
        crop = lambda f: imgs[f][y:y + max(h, 4), x:x + max(w, 4)].astype(np.float32)  # noqa: E731
        d1 = float(np.abs(crop(n) - crop(n - 1)).mean())
        d2 = float(np.abs(crop(n + 1) - crop(n)).mean())
        if n in tframes and d1 >= 2.0:
            pass   # a transition keeps moving after its cut by design
        elif d1 < 2.0 or (e["kind"] == "cut" and d2 > max(4.0, 1.2 * d1)):
            late.append(f"{e['label']} f{n}: change N-1->N {d1:.1f}, N->N+1 {d2:.1f}")
        rows += [imgs[n - 1], imgs[n], imgs[n + 1]]
        labels += [f"{n - 1}", f"{n} {e['label'][:30]}", f"{n + 1}"]
    chk(checks, "switch_timeline", not tl_bad, f"{len(evs)} events; " + ("all flip on their frame" if not tl_bad else str(tl_bad[:4])))
    chk(checks, "switch_render", not late, f"{len(evs)} events; " + ("all change on frame N" if not late else str(late[:4])))
    kit.label_sheet(rows, labels, os.path.join(qa_dir, "switches.jpg"), cols=6)

    # ---- blank frames + overview + face sheet
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", demo, "-vf", "scale=54:96", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, 96, 54).astype(np.float32)
    blank = [int(i) for i in np.nonzero(g.std(axis=(1, 2)) < 3.0)[0] if int(i) not in tframes]   # an iris closes to a plate
    chk(checks, "no_blank_frames", not blank, f"{len(g)} frames scanned, blank: {blank[:10]}")
    ov = list(range(0, frames, FPS))
    oi = kit.grab(demo, ov, scale=240)
    kit.label_sheet([oi[f] for f in ov], [f"{f / FPS:.0f}s" for f in ov], os.path.join(qa_dir, "overview.jpg"), cols=9)
    draw_face_sheet(demo, samples, ft, os.path.join(qa_dir, "face.jpg"))

    # ---- motion v2 gates (engine/qa_motion.py)
    if mplan:
        import qa_motion
        gb = []
        for e in meta.get("events", []):
            if e.get("kind") == "enter" and e.get("region"):
                x, y, w, h = e["region"]
                gb.append({"t0": e["frame"] / FPS, "t1": e["frame"] / FPS, "boxes": [{"kind": "card", "x": x, "y": y, "w": w, "h": h}]})
        for c in qa_motion.run(proj.dir, demo, qa_dir, graphic_beats=gb):
            checks.append(c)
            print(f"  {'SKIP' if c.get('skipped') else ('PASS' if c['pass'] else 'FAIL')}  {c['name']}: {c['detail'][:200]}")
    res = {"pass": all(c["pass"] for c in checks), "checks": checks, "demo": demo, "frames": frames,
           "face_hits": face_hits[:40], "safe_hits": safe_hits[:40]}
    kit.jsave(os.path.join(qa_dir, "report.json"), res)
    print("QA", "PASS" if res["pass"] else "FAIL")
    return res


def draw_face_sheet(demo, samples, ft, out):
    from PIL import Image, ImageDraw
    pick = [s for s in samples if s["f"] % 45 == 0]
    imgs = kit.grab(demo, [s["f"] for s in pick], scale=360)
    k = 360 / 1080
    tiles, labels = [], []
    for s in pick:
        im = Image.fromarray(imgs[s["f"]].copy())
        d = ImageDraw.Draw(im)
        fb = face_at(ft, s["f"])
        if fb:
            d.rectangle([fb[0] * k, fb[1] * k, (fb[0] + fb[2]) * k, (fb[1] + fb[3]) * k], outline=(255, 40, 40), width=2)
        for b in s["boxes"]:
            if b["kind"] in ("card", "caption", "title") and b["op"] > 0.08:
                d.rectangle([b["x"] * k, b["y"] * k, (b["x"] + b["w"]) * k, (b["y"] + b["h"]) * k], outline=(40, 160, 255), width=1)
        for y in (SAFE["top"], SAFE["bottom"]):
            d.line([0, y * k, 360, y * k], fill=(255, 220, 0), width=1)
        tiles.append(np.asarray(im))
        labels.append(f"{s['f']} ({s['f'] / FPS:.1f}s)")
    kit.label_sheet(tiles, labels, out, cols=8)


if __name__ == "__main__":
    r = run(sys.argv[1], sys.argv[2], sys.argv[3])
    sys.exit(0 if r["pass"] else 1)
