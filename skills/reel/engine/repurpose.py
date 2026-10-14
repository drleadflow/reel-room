"""Repurpose a posted reel: remove the old burned-in title, captions and cards so they never show under the new style.

Workflow
  1. Download the posted reel (720p or 1080p, text burned into the picture).
  2. repurpose.py detect <video> --out P/work/repurpose.json --sheet P/work/repurpose_sheet.jpg
       proposes regions: static titles (top 30%), the caption band with per-frame extents, and dark/light cards.
  3. LOOK at the sheet. Fix P/work/repurpose.json by hand: boxes, frame windows, methods (see below). Add anything
     detect missed (it writes a "todo" example). Re-run with --sheet only (`detect ... --redraw`) to redraw your edits.
  4. repurpose.py bake <video> P/work/repurpose.json P/assets/plate_clean.mp4 --frames 0-240 --check P/work/check.jpg
       first on a short window, look at the check jpg, then without --frames for the whole plate.
  5. ingest.py P P/assets/plate_clean.mp4  (the clean plate is the clip), then the normal build.
  Record it in project.json: "repurpose": {"src": "<download>", "regions": "work/repurpose.json",
  "plate": "assets/plate_clean.mp4"}. Hide by layout instead: `repurpose.py crop` prints a 9:16 crop that keeps the title
  and caption bands out of frame, as zoom/cx/cy for edl.json.

Methods (per region)
  blur     feathered heavy blur + tint toward "fill" (default #121014). Interior fully covered. Cards, caption band.
  inpaint  TELEA over a glyph mask ("mask": "glyph": pixels text-like in > 85% of the window) or the whole box. Best on
           flat walls; over hair or faces it smears, use blur or ref there.
  ref      median of clean reference frames "ref_frames": [a,b] (locked-off camera only), feathered.
  interp   column-wise interpolation between the rows above and below the box + noise. Flat walls, tight boxes.
Region keys: id, kind, method, box [x0,y0,x1,y1] in SOURCE px, frames [f0,f1] | "all", per_frame {"<f>": [x0,x1]},
  mask, ref_frames, tint, fill, sigma, feather, pad. Frames are 0-based source frame numbers, inclusive.

Usage
  repurpose.py detect <video> [--out regions.json] [--sheet sheet.jpg] [--step 3] [--redraw] [--json]
  repurpose.py bake <video> <regions.json> <out.mp4> [--frames A-B] [--size 1080x1920] [--crf 15] [--check check.jpg]
  repurpose.py crop <video> <regions.json> [--size 1080x1920] [--cx 0.5] [--json]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import repurpose_ops as O  # noqa: E402

TITLE_TOP = 0.30
COLOURS = {"title": (60, 60, 255), "caption": (0, 220, 255), "card": (255, 160, 0)}


# ----------------------------------------------------------------------------- video io
def need_cv2():
    if O.cv2 is None:
        C.fail("OpenCV is not installed in this Python.", "Run doctor.py, or use the Reel Room venv python.")
    return O.cv2


def video_info(path):
    if not Path(path).exists():
        C.fail(f"Video not found: {path}", "Pass the downloaded reel file (absolute path).")
    cap = need_cv2().VideoCapture(str(path))
    info = {**C.probe(path), "n": int(cap.get(7))}
    cap.release()
    return info


def frames(path, a=0, b=None, step=1):
    """yield (i, frame) for a <= i <= b, every step-th frame (decodes only what it yields)"""
    cap = need_cv2().VideoCapture(str(path))
    i = 0
    try:
        while b is None or i <= b:
            if i < a or (i - a) % step:
                if not cap.grab():
                    break
            else:
                ok, f = cap.read()
                if not ok:
                    break
                yield i, f
            i += 1
    finally:
        cap.release()


def load_regions(path):
    try:
        data = C.read_json(path)
    except FileNotFoundError:
        C.fail(f"Regions file not found: {path}", "Run repurpose.py detect first (it writes the regions file).")
    except ValueError as e:
        C.fail(f"Regions file {path} is not valid JSON: {e}", "Fix the JSON syntax (a missing comma or bracket).")
    regs = data.get("regions", []) if isinstance(data, dict) else data
    for r in regs:
        if "box" not in r or len(r["box"]) != 4:
            C.fail(f"Region {r.get('id')} has no box [x0,y0,x1,y1].", "Add a box in source pixels.")
        if r.get("method", "blur") not in O.METHODS:
            C.fail(f"Region {r.get('id')} has method {r.get('method')!r}.", f"Use one of {', '.join(O.METHODS)}.")
    return data, regs


# ----------------------------------------------------------------------------- detect
def sample_pass(video, info, step):
    """sampled pass: title glyph masks (top band) and caption glyph counts per row (search band)"""
    top, lo, hi = (int(v * info["h"]) for v in (TITLE_TOP, 0.40, 0.85))
    titles, rows = [], O.np.zeros(info["h"])
    for i, f in frames(video, step=step):
        titles.append((i, O.thin_text(f[:top], pill=True).astype(bool)))
        rows[lo:hi] += O.thin_text(f[lo:hi], colour=False).sum(1)
    return titles, rows


def full_pass(video, info, band, card_step):
    """every frame: caption extents inside the band; every card_step-th frame: card candidates above the band"""
    p = int(10 * O.scale_of(info["w"]))
    per, cards = {}, []
    for i, f in frames(video):
        ex = O.caption_extent(f, band[0], band[1]) if band else None
        if ex:
            per[str(i)] = [max(0, ex[0] - p), min(info["w"], ex[1] + p)]
        if i % card_step == 0:
            cards.append((i, O.card_candidates(f, band[0] if band else None)))
    return per, cards


def title_regions(titles, step, w, n):
    s = O.scale_of(w)
    out = []
    for f0, f1, st in O.static_windows(titles, step, min_len=2):
        f0, f1 = max(0, f0 - 2 * step), min(n - 1, f1 + 2 * step)
        for bx in O.blobs(st, merge=40 * s, min_area=150 * s * s):
            p = int(10 * s)
            box = [max(0, bx[0] - p), max(0, bx[1] - p), min(w, bx[2] + p), bx[3] + p]
            out.append({"id": f"title{len(out) + 1}", "kind": "title", "method": "inpaint", "mask": "glyph",
                        "box": box, "frames": [f0, f1]})
    return out


def text_px(f, box):
    x0, y0, x1, y1 = box
    return int(O.thin_text(f[y0:y1, x0:x1], pill=True).sum())


def is_cut(f, g, thr=20.0):
    sm = lambda x: O.cv2.resize(O.cv2.cvtColor(x, O.cv2.COLOR_BGR2GRAY), (45, 80)).astype(O.np.float32)  # noqa: E731
    return float(O.np.abs(sm(f) - sm(g)).mean()) > thr


def stroke_ratio(f, box):
    """share of the title glyphs that have a dark outline (low = text on a pill or panel)"""
    x0, y0, x1, y1 = box
    sub = f[y0:y1, x0:x1]
    return O.thin_text(sub).sum() / max(1, O.thin_text(sub, pill=True).sum())


def trim_window(got, box, f0, f1, fade=8):
    """shrink a title window to the frames that show ITS text (per-frame text mask overlaps the window's majority mask,
    so a different title at the same spot does not count), plus up to `fade` frames each side, never across a cut"""
    x0, y0, x1, y1 = box
    tl = {i: O.text_like(got[i][y0:y1, x0:x1]) for i in range(f0, f1 + 1) if i in got}
    if not tl:
        return f0, f1
    big = max(int(m.sum()) for m in tl.values())
    sel = [m for m in tl.values() if m.sum() > 0.5 * big] if big else list(tl.values())
    core = O.np.mean(sel[::max(1, len(sel) // 24)], axis=0) > 0.5
    sim = {i: O.iou(m, core) for i, m in tl.items()}
    top = max(sim.values())
    on = [i for i, v in sim.items() if v > 0.6 * top] if top > 0 else []
    if not on:
        return f0, f1
    a, b = on[0], on[-1]
    for _ in range(fade):
        if a - 1 in got and not is_cut(got[a - 1], got[a]):
            a -= 1
        if b + 1 in got and not is_cut(got[b + 1], got[b]):
            b += 1
    return a, b


def refine_title(video, info, r, gap=4, span=24):
    """trim the window to the text, widen to the pill when the text sits on one, then try method ref"""
    n, w, h = info["n"], info["w"], info["h"]
    lo, hi = max(0, r["frames"][0] - gap - span), min(n - 1, r["frames"][1] + gap + span)
    a, b = r["frames"]  # dense near the window edges, every 6th frame inside it (memory)
    got = {i: f for i, f in frames(video, lo, hi) if i <= a + 32 or i >= b - 32 or i % 6 == 0}
    box = O.clip_box(r["box"], w, h)
    f0, f1 = trim_window(got, box, *r["frames"])
    r = {**r, "frames": [f0, f1]}
    win = [got[i] for i in range(f0, f1 + 1) if i in got]
    if not win:
        return r
    pb = None
    if stroke_ratio(win[len(win) // 2], box) < 0.3:  # no dark outline: the text sits on a pill or panel
        pb = O.pill_box(win[len(win) // 2], box) or O.grow_box(box, int(12 * O.scale_of(w)))
    if pb:  # flat pill behind the text: fill the whole pill from the wall above and below it
        r = {k: v for k, v in r.items() if k != "mask"}
        r.update(box=pb, method="interp", pill=True)
        box = O.clip_box(pb, w, h)
    return try_ref(got, r, box, win, w, gap, span)


def try_ref(got, r, box, win, w, gap, span):
    """method ref when clean frames right after (or before) the window show the same shot: no text in the box and the
    area around the text matches (locked-off camera)"""
    np, (f0, f1) = O.np, r["frames"]
    mask = O.glyph_mask(win[::max(1, len(win) // 12)], box)
    on = max(1, np.mean([text_px(f, box) for f in win]))
    ring = O.clip_box(O.grow_box(box, int(20 * O.scale_of(w))), w, len(mask))
    keep = mask[ring[1]:ring[3], ring[0]:ring[2]] == 0
    for a, b in ((f1 + gap, f1 + gap + span), (f0 - gap - span, f0 - gap)):
        cand = [got[i] for i in range(a, b + 1, 2) if i in got]
        if len(cand) < 6 or max(text_px(f, box) for f in cand) > 0.05 * on:
            continue
        ref = np.median(np.stack(cand), axis=0)[ring[1]:ring[3], ring[0]:ring[2]]

        def same(i):  # median: other titles nearby must not veto
            d = np.abs(got[i][ring[1]:ring[3], ring[0]:ring[2]].astype(np.float32) - ref).mean(-1)[keep]
            return d.size > 0 and float(np.median(d)) < 6

        if all(same(i) for i in range(f0, f1 + 1, max(1, (f1 - f0) // 4)) if i in got):
            span_ok = [f0, a - 1] if a > f1 else [b + 1, f1]  # same shot up to the clean frames: covers the fade
            return {**r, "method": "ref", "ref_frames": [a, b], "frames": span_ok}
    return r


def caption_region(per, band):
    if not per:
        return None
    xs = list(per.values())
    return {"id": "captions", "kind": "caption", "method": "blur", "box": [min(x[0] for x in xs), band[0],
            max(x[1] for x in xs), band[1]], "frames": "all", "per_frame": per, "tint": 0.4, "pad": 0}


def card_regions(found, step, info):
    out = []
    for f0, f1, box in O.track_boxes(found, step):
        out.append({"id": f"card{len(out) + 1}", "kind": "card", "method": "blur", "box": box,
                    "frames": [max(0, f0 - 2 * step), min(info["n"] - 1, f1 + 2 * step)],
                    "pad": int(8 * O.scale_of(info["w"])), "check": "card bottoms are estimated: check y1 on the sheet"})
    return out


TODO = {"id": "todo-example", "kind": "card", "method": "blur", "box": [20, 600, 700, 920], "frames": [0, 0], "tint": 0.42,
        "fill": "#100C14", "note": "anything detect missed: copy into regions, set box/frames from the sheet"}


def cmd_detect(a):
    out = Out(a.json)
    info = video_info(a.video)
    dest = Path(a.out or Path.cwd() / (Path(a.video).stem + ".regions.json"))  # never beside the download
    if a.redraw:
        _, regs = load_regions(dest)
    else:
        titles, rows = sample_pass(a.video, info, a.step)
        regs = [refine_title(a.video, info, r) for r in title_regions(titles, a.step, info["w"], info["n"])]
        band = O.find_band(rows, info["h"])
        per, found = full_pass(a.video, info, band, a.step * 2)
        cap = caption_region(per, band)
        regs += card_regions(found, a.step * 2, info) + ([cap] if cap else [])
        C.write_json(dest, {"src": str(Path(a.video).resolve()), "w": info["w"], "h": info["h"], "fps": info["fps"],
                            "frames": info["n"], "regions": regs, "todo": [TODO]})
    sheet = Path(a.sheet or dest.with_suffix(".jpg"))
    draw_sheet(a.video, info, regs, sheet)
    summary = [{"id": r["id"], "method": r["method"], "box": r["box"], "frames": r["frames"],
                "per_frame": len(r.get("per_frame") or {})} for r in regs]
    out.result({"regions": str(dest), "sheet": str(sheet), "found": summary})


# ----------------------------------------------------------------------------- sheets
def label(img, text, xy, col=(255, 255, 255)):
    cv2 = O.cv2
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)


def sheet_frames(info, regs, k=10):
    n = info["n"]
    want = {int(n * (j + 0.5) / k) for j in range(k)}
    for r in regs:
        f0, f1 = O.parse_range(r.get("frames", "all"), n)
        if r.get("per_frame"):
            keys = sorted(int(x) for x in r["per_frame"])
            want.add(keys[len(keys) // 2])
        else:
            want.add((f0 + f1) // 2)
    return sorted(want)[:24]


def draw_sheet(video, info, regs, dest, tile_w=270):
    cv2 = O.cv2
    want = sheet_frames(info, regs)
    tiles = []
    for i, f in frames(video, 0, max(want)):
        if i not in want:
            continue
        im = f.copy()
        for r in regs:
            bx = O.region_box(r, i, info["n"], info["w"], info["h"])
            if bx:
                col = COLOURS.get(r.get("kind"), (0, 255, 0))
                cv2.rectangle(im, bx[:2], bx[2:], col, max(2, info["w"] // 300))
                label(im, f"{r['id']} {r.get('method')}", (bx[0] + 4, bx[1] + 18), col)
        im = cv2.resize(im, (tile_w, int(tile_w * info["h"] / info["w"])), interpolation=cv2.INTER_AREA)
        label(im, f"f{i}", (6, 18), (0, 255, 0))
        tiles.append(im)
    write_grid(tiles, dest, cols=6)


def write_grid(tiles, dest, cols):
    cv2, np = O.cv2, O.np
    if not tiles:
        C.fail("Nothing to draw on the sheet.", "Check the video decodes: ffprobe it, or re-download.")
    th, tw = tiles[0].shape[:2]
    while len(tiles) % cols:
        tiles.append(np.zeros((th, tw, 3), np.uint8))
    rows = [np.hstack(tiles[j:j + cols]) for j in range(0, len(tiles), cols)]
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


# ----------------------------------------------------------------------------- bake
def build_ctx(video, info, regs):
    """per-region precomputed glyph masks (mask: glyph) and clean reference images (method ref)"""
    np, n = O.np, info["n"]
    need = {}
    for r in regs:
        if r.get("mask") == "glyph":
            f0, f1 = O.parse_range(r.get("frames", "all"), n)
            need[r["id"]] = {"mask": sorted({int(f0 + (f1 - f0) * j / 23) for j in range(24)})}
        if r.get("method") == "ref":
            if not r.get("ref_frames"):
                C.fail(f"Region {r['id']} uses method ref without ref_frames.", 'Add "ref_frames": [a, b] (clean frames).')
            a, b = O.parse_range(r["ref_frames"], n)
            need.setdefault(r["id"], {})["ref"] = sorted({int(a + (b - a) * j / 14) for j in range(15)})
    wanted = {f for v in need.values() for fl in v.values() for f in fl}
    got = {i: f for i, f in frames(video, 0, max(wanted)) if i in wanted} if wanted else {}
    ctx = {}
    for rid, v in need.items():
        r = next(x for x in regs if x["id"] == rid)
        c = ctx.setdefault(rid, {})
        if "mask" in v:
            c["mask"] = O.glyph_mask([got[i] for i in v["mask"] if i in got], r["box"])
        if "ref" in v:
            c["ref"] = np.median(np.stack([got[i] for i in v["ref"] if i in got]), axis=0).astype(np.uint8)
    return ctx


def fit_size(img, ow, oh):
    """scale to cover ow x oh, centre-crop the overflow"""
    cv2 = O.cv2
    h, w = img.shape[:2]
    k = max(ow / w, oh / h)
    nw, nh = max(ow, round(w * k)), max(oh, round(h * k))
    im = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4 if k > 1 else cv2.INTER_AREA)
    x, y = (nw - ow) // 2, (nh - oh) // 2
    return im[y:y + oh, x:x + ow]


def encoder(video, info, out, size, a, b, crf):
    fps = info["fps"] or 30
    cmd = [C.ffmpeg_bin(), "-hide_banner", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-"]
    if info.get("has_audio"):
        cmd += ["-ss", f"{a / fps:.4f}", "-t", f"{(b - a + 1) / fps:.4f}", "-i", str(video), "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-colorspace", "bt709", "-g", "30"]
    if info.get("has_audio"):
        cmd += ["-c:a", "aac", "-b:a", "256k", "-shortest"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(cmd + [str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def check_points(regs, n, a, b):
    """{frame: [region ids]} at the middle of every region window inside a..b"""
    pts = {}
    for r in regs:
        f0, f1 = O.parse_range(r.get("frames", "all"), n)
        if r.get("per_frame"):
            keys = [int(k) for k in r["per_frame"] if a <= int(k) <= b]
            mid = sorted(keys)[len(keys) // 2] if keys else None
        else:
            lo, hi = max(a, f0), min(b, f1)
            mid = (lo + hi) // 2 if lo <= hi else None
        if mid is not None:
            pts.setdefault(mid, []).append(r["id"])
    return pts


def zoom_tile(after, crops, tw, th):
    """the region crops (after the bake) scaled to the tile width, stacked top to bottom"""
    np, cv2 = O.np, O.cv2
    tile, y = np.zeros((th, tw, 3), np.uint8), 0
    for x0, y0, x1, y1 in crops:
        z = after[y0:y1, x0:x1]
        if not z.size:
            continue
        zh = max(1, int(tw * z.shape[0] / z.shape[1]))
        z = cv2.resize(z, (tw, zh), interpolation=cv2.INTER_CUBIC)[:th - y]
        tile[y:y + z.shape[0]] = z
        y += z.shape[0] + 4
        if y >= th:
            break
    return tile


def check_tiles(before, after, ids, regs, i, info, tw=300):
    """before (boxes drawn) | after | after, zoomed into each region"""
    cv2 = O.cv2
    th = int(tw * info["h"] / info["w"])
    b, crops, m = before.copy(), [], int(20 * O.scale_of(info["w"]))
    for r in (x for x in regs if x["id"] in ids):
        bx = O.region_box(r, i, info["n"], info["w"], info["h"])
        if bx:
            cv2.rectangle(b, bx[:2], bx[2:], COLOURS.get(r.get("kind"), (0, 255, 0)), 2)
            crops.append(O.clip_box(O.grow_box(bx, m), info["w"], info["h"]))
    out = [cv2.resize(b, (tw, th)), cv2.resize(after, (tw, th)), zoom_tile(after, crops, tw, th)]
    for t, txt in zip(out, (f"f{i} before {','.join(ids)}", "after", "after, zoom")):
        label(t, txt, (6, th - 8 if txt.startswith("after, z") else 18), (0, 255, 0))
    return out


def cmd_bake(a):
    out = Out(a.json)
    info = video_info(a.video)
    _, regs = load_regions(a.regions)
    try:
        f0, f1 = O.parse_range(a.frames or "all", info["n"])
        size = [int(v) for v in a.size.lower().split("x")]
    except ValueError as e:
        C.fail(str(e), "Use --frames 0-240 and --size 1080x1920.")
    ctx = build_ctx(a.video, info, regs)
    pts = check_points(regs, info["n"], f0, f1) if a.check else {}
    enc, tiles, count = encoder(a.video, info, a.out, size, f0, f1, a.crf), [], 0
    try:
        for i, f in frames(a.video, f0, f1):
            g = f
            for r in regs:
                g = O.apply_region(g, r, i, info["n"], ctx.get(r["id"]))
            if i in pts:
                tiles += check_tiles(f, g, pts[i], regs, i, info)
            enc.stdin.write(fit_size(g, *size).tobytes())
            count += 1
    except (BrokenPipeError, ValueError) as e:
        enc.kill()
        C.fail(f"Bake stopped at frame {f0 + count}: {e}", "Read the message above; fix regions.json and re-run.")
    err = enc.communicate()[1].decode(errors="replace")  # closes stdin, waits, drains stderr
    if enc.returncode != 0:
        C.fail("ffmpeg could not encode the plate: " + err[-300:], "Run doctor.py to check ffmpeg.")
    if a.check and tiles:
        write_grid(tiles, a.check, cols=6)
    out.result({"out": str(a.out), "frames": count, "range": [f0, f1], "size": size,
                "check": str(a.check) if a.check else None, "checked_frames": sorted(pts)})


# ----------------------------------------------------------------------------- crop
def cmd_crop(a):
    out = Out(a.json)
    info = video_info(a.video)
    _, regs = load_regions(a.regions)
    try:
        ow, oh = (int(v) for v in a.size.lower().split("x"))
        plan = O.crop_plan(info["w"], info["h"], regs, ow, oh, a.cx)
    except ValueError as e:
        C.fail(str(e), "Use repurpose.py bake to cover the text instead.")
    plan["edl"] = {"zoom": plan["zoom"], "cx": plan["cx"], "cy": plan["cy"]}
    if plan["upscale"] > 2.0:
        plan["warning"] = f"upscale {plan['upscale']}x from {info['w']}x{info['h']}: expect soft picture"
    out.result(plan)


class Out(C.Out):
    def result(self, data):
        if self.json:
            return super().result(data)
        for k, v in data.items():
            print(f"{k}: {v}")


def main():
    ap = argparse.ArgumentParser(description="Remove burned-in text from a posted reel (see the module docstring).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d, b, c = sub.add_parser("detect"), sub.add_parser("bake"), sub.add_parser("crop")
    for p in (d, b, c):
        p.add_argument("video")
        p.add_argument("--json", action="store_true")
    for p in (b, c):
        p.add_argument("regions")
        p.add_argument("--size", default="1080x1920")
    d.add_argument("--out")
    d.add_argument("--sheet")
    d.add_argument("--step", type=int, default=3)
    d.add_argument("--redraw", action="store_true", help="redraw the sheet from an edited regions file")
    b.add_argument("out")
    b.add_argument("--frames")
    b.add_argument("--crf", type=int, default=15)
    b.add_argument("--check")
    c.add_argument("--cx", type=float, default=0.5)
    a = ap.parse_args()
    {"detect": cmd_detect, "bake": cmd_bake, "crop": cmd_crop}[a.cmd](a)


if __name__ == "__main__":
    C.reexec_in_venv()
    main()
