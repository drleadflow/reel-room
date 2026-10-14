"""report.py: the QA contract pieces of a composition (layout_boxes.json): per-slice boxes, the frame-exact duration,
jump-cut warnings, and the picture-in-picture face mask (a head bubble moves the face off the plate)."""
import json

import timeline as tl_

KIND = {"caption": "caption", "text": "text", "glyph": "text", "card": "card", "polaroid": "card", "image": "insert", "video": "insert"}


def qa_beats(placement, boxes):
    """qa contract: one entry per cut/layout slice with every on-screen box (frame px, cut-time s) and the face box."""
    out = []
    for s in placement:
        bx = []
        for b in boxes:
            t0, t1 = max(b["t0"], s["t0"]), min(b["t1"], s["t1"])
            if t1 - t0 < 0.04:
                continue
            bx.append({"kind": KIND.get(b["kind"], "insert"), "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"],
                       "t0": round(t0, 3), "t1": round(t1, 3), "text": b.get("text", ""), "readable": b["readable"],
                       **({"style": b["style"]} if b.get("style") else {}), **({"color": b["color"]} if b.get("color") else {}),
                       **({"beat": b["beat"]} if b.get("beat") else {})})
        f = s.get("face")
        if f:
            bx.append({"kind": "face", "x": round(f["cx"] - f["w"] / 2), "y": round(f["cy"] - f["h"] / 2), "w": f["w"], "h": f["h"],
                       "t0": round(s["t0"], 3), "t1": round(s["t1"], 3), "text": "", "readable": False})
        out.append({"t0": round(s["t0"], 3), "t1": round(s["t1"], 3), "layout": s["layout"], "seg": s["seg"], "boxes": bx})
    return out


def frame_duration(frames):
    """Seconds string for the root/aroll duration such that ceil(d * FPS) == frames (HyperFrames renders ceil)."""
    ms = frames * 1000 // tl_.FPS
    while -(-ms * tl_.FPS // 1000) != frames:
        ms -= 1
        if ms <= 0:
            raise SystemExit(f"cannot derive a duration for {frames} frames")
    return f"{ms // 1000}.{ms % 1000:03d}"


def beat_sig(b):
    return (b["layout"], json.dumps(b["items"], sort_keys=True))


def jump_cut_warnings(segs, beats, punches, marks=()):
    """A jump cut must land on a layout change, a new insert, a framing change (punch-in), or a picture change an
    insert registered on that cut frame (cx.cut_change)."""
    out = []
    at = lambda t: next((b for b in beats if b["t0"] - 1e-4 <= t < b["t1"] - 1e-4), beats[-1])  # noqa: E731
    for a, b in zip(segs, segs[1:]):
        ba, bb = at(a["t0"] + 1e-3), at(b["t0"] + 1e-3)
        if ba is bb or beat_sig(ba) == beat_sig(bb):
            fa = a.get("zoom", 1) * punches.get(a["id"], 1.0)
            fb = b.get("zoom", 1) * punches.get(b["id"], 1.0)
            if abs(fa - fb) > 0.05:
                continue  # the framing changes on the cut (punch-in / pull-out)
            if any(abs(b["t0"] - m) < 0.02 for m in marks):
                continue  # an insert changes the picture on this cut frame
            out.append(f"jump cut {a['id']} -> {b['id']} at {b['t0']:.2f}s: same {ba['layout']} layout, same insert and "
                       f"same framing. Change layout, give {b['id']} its own insert, or set a punch.")
    return out


def pip_mask(placement, windows):
    """Placement for QA with the plate's face hidden inside each picture-in-picture window [(t0, t1), ...]: slices are
    split at the window edges and the inside parts marked visible False / pip True (the face is in the bubble, the
    full-screen graphic covers the plate; face checks skip those frames). The render placement is not changed."""
    out = [dict(p) for p in placement]
    for a, b in sorted(windows or []):
        nxt = []
        for p in out:
            if p["t1"] <= a + 1e-4 or p["t0"] >= b - 1e-4:
                nxt.append(p)
                continue
            for lo, hi, inside in ((p["t0"], a, False), (max(p["t0"], a), min(p["t1"], b), True), (b, p["t1"], False)):
                if hi - lo > 1e-4:
                    q = {**p, "t0": round(lo, 4), "t1": round(hi, 4)}
                    if inside:
                        q.update(visible=False, pip=True, face=None)
                    nxt.append(q)
        out = nxt
    return out
