"""deck.py: split-deck Motion v2 phase 3, the "deck camera" on the top panel.

The panel content of every split beat sits in its own camera wrapper (`.dcam`, `#<beat>cam`) inside the beat (the beat
keeps its 1080x960 clip, so a push never crosses the seam). Per frame (RRM.keys, seek-safe) the deck camera:
  - pushes slowly through the beat (no dead panel)
  - glides toward the item that just landed (a row ticks, a value lands): `focus` cues registered by the inserts
  - punches on hero hits (`punch` cues)
  - swaps panel content with a push-through when two split beats meet on a cut that has no whole-frame transition
    (old content leaves up in 4 frames, new content rises in 7 frames under a motion blur)
Every transformed frame is clamped against the beat's MEASURED boxes, so readable content stays inside y 226-952 and
x 40-1040 (safe zone, never under the seam).

On by default for split-deck (`style` none or "split-deck") at polished / showreel. Opt in from any split-engine style
with project.json "motion": {"deck": true}; "deck": false switches it off.
"""
import json

FPS = 30
C = (540.0, 585.0)          # deck camera origin (panel centre)
TOP, BOT, LEFT, RIGHT = 226.0, 952.0, 40.0, 1040.0
FOCUS_DUR, FOCUS_LEAD = 0.62, 0.14
ENTER_F, EXIT_F = 7, 4


def enabled(style_mod, pj, mcfg):
    """True when the deck camera runs for this composition."""
    if not mcfg or mcfg.get("level") == "simple":
        return False
    m = pj.get("motion") if isinstance(pj.get("motion"), dict) else {}
    if "deck" in m:
        return bool(m["deck"])
    return style_mod is None


def focus(cx, beat, t, x, y, k=1.1, what=""):
    """Register a deck camera focus: at time t the camera glides toward frame point (x, y), scale k."""
    cx.deck_focus.append({"beat": beat["id"], "t": float(t), "x": float(x), "y": float(y), "k": float(k),
                          "kind": "focus", "what": what})


def punch(cx, beat, t, k=1.05, what=""):
    cx.deck_focus.append({"beat": beat["id"], "t": float(t), "k": float(k), "kind": "punch", "what": what})


def _ease_io(p):
    p = min(1.0, max(0.0, p))
    return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2


def _eout(p, n=3):
    return 1 - (1 - min(1.0, max(0.0, p))) ** n


def _bbox(boxes, bid):
    """Union of the beat's measured graphic boxes (frame px) or None."""
    bx = [b for b in boxes or [] if b.get("beat") == bid and b.get("kind") not in ("caption",) and b["w"] > 0]
    if not bx:
        return None
    return (min(b["x"] for b in bx), min(b["y"] for b in bx), max(b["x"] + b["w"] for b in bx),
            max(b["y"] + b["h"] for b in bx))


def _target(f, bb):
    """(s, tx, ty) that brings focus point P half way to the panel centre at scale k."""
    a = 0.5
    k = f["k"]
    tx = (1 - a - k) * (f["x"] - C[0])
    ty = (1 - a - k) * (f["y"] - C[1])
    return (k, tx, ty)


def _clamp(s, tx, ty, bb):
    x0, y0, x1, y1 = bb
    s = min(s, max(1.0, (BOT - TOP) / max(1.0, y1 - y0)), max(1.0, (RIGHT - LEFT) / max(1.0, x1 - x0)))
    lo_y, hi_y = TOP - C[1] - s * (y0 - C[1]), BOT - C[1] - s * (y1 - C[1])
    lo_x, hi_x = LEFT - C[0] - s * (x0 - C[0]), RIGHT - C[0] - s * (x1 - C[0])
    ty = (lo_y + hi_y) / 2 if lo_y > hi_y else min(max(ty, lo_y), hi_y)
    tx = (lo_x + hi_x) / 2 if lo_x > hi_x else min(max(tx, lo_x), hi_x)
    return s, tx, ty


def _state(t, b, cues, bb, push_amt):
    """Camera (s, tx, ty) at time t inside beat b."""
    dur = max(1e-3, b["t1"] - b["t0"])
    s, tx, ty = 1.0, 0.0, 0.0
    for c in [c for c in cues if c["kind"] == "focus"]:
        t0 = c["t"] - FOCUS_LEAD
        if t < t0:
            break
        p = _ease_io((t - t0) / FOCUS_DUR)
        ts, ttx, tty = _target(c, bb)
        s, tx, ty = s + (ts - s) * p, tx + (ttx - tx) * p, ty + (tty - ty) * p
    s *= 1.0 + push_amt * min(1.0, max(0.0, (t - b["t0"]) / dur))
    for c in [c for c in cues if c["kind"] == "punch"]:
        pp = (t - c["t"]) / 0.24
        if 0 <= pp < 1:
            s *= 1 + (c["k"] - 1) * (1 - pp) ** 3
    return _clamp(s, tx, ty, bb)


def _swap_rows(f0, f1, enter, leave):
    """Per-frame (dy, blur, o) of the panel swap: rise in over ENTER_F frames, leave up over the last EXIT_F."""
    out = {}
    if enter:
        for j in range(ENTER_F):
            p = _eout((j + 1) / (ENTER_F + 1), 4)
            out[f0 + j] = (round(110 * (1 - p), 1), round(9 * (1 - p), 1), round(0.8 + 0.2 * p, 3))
    if leave:
        for j in range(EXIT_F):
            p = ((j + 1) / EXIT_F) ** 2
            out[f1 - EXIT_F + j] = (round(-170 * p, 1), round(12 * p, 1), round(1 - 0.7 * p, 3))
    return out


def plan(cx, beats, boxes, transitions):
    """-> (js lines, events, report). transitions: the motion plan's whole-frame transitions (they own their cuts)."""
    t_frames = set()
    for tr in transitions or []:
        t_frames |= set(range(tr["span"][0], tr["span"][1] + 1))
    split = [b for b in beats if b.get("items") and b["layout"] == "split" and not _feed(b)]
    by_t0 = {round(b["t0"], 3): b for b in beats if b.get("items")}
    js, events, rep = [], [], {"beats": 0, "focus": 0, "punch": 0, "swaps": 0}
    for b in split:
        f0, f1 = int(round(b["t0"] * FPS)), int(round(b["t1"] * FPS))
        if f1 - f0 < 3:
            continue
        bb = _bbox(boxes, b["id"]) or (120.0, 300.0, 960.0, 880.0)
        cues = sorted([c for c in cx.deck_focus if c["beat"] == b["id"]], key=lambda c: c["t"])
        nxt = by_t0.get(round(b["t1"], 3))
        prv = next((x for x in beats if x.get("items") and abs(x["t1"] - b["t0"]) < 1e-3), None)
        enter = bool(prv and prv["layout"] == "split" and f0 not in t_frames and not _feed(prv))
        leave = bool(nxt and nxt["layout"] == "split" and f1 not in t_frames and f1 - f0 > EXIT_F + ENTER_F + 6
                     and not _feed(nxt))
        swap = _swap_rows(f0, f1, enter, leave)
        push_amt = min(0.05, 0.008 * (b["t1"] - b["t0"]) + 0.012)
        rows, prev = [], None
        for f in range(f0, f1):
            s, tx, ty = _state(f / FPS, b, cues, bb, push_amt)
            dy, blur, o = swap.get(f, (0.0, 0.0, 1.0))
            row = [f, round(s, 4), round(tx, 1), round(ty + dy, 1), blur, o]
            if prev is None or row[1:] != prev[1:]:
                rows.append(row)
            prev = row
        js.append(f"RRM.keys(tl,'#{b['id']}cam',['scale','x','y','blur','o']," + json.dumps(rows, separators=(",", ":")) + ");")
        for c in cues:
            events.append({"t": round(c["t"], 3), "kind": "push" if c["kind"] == "focus" else "punch",
                           "what": f"deck {c.get('what', '')}".strip(), "src": "motion"})
        if enter:
            events.append({"t": round(b["t0"], 3), "kind": "swap", "what": "deck swap in", "src": "motion"})
        rep["beats"] += 1
        rep["focus"] += sum(1 for c in cues if c["kind"] == "focus")
        rep["punch"] += sum(1 for c in cues if c["kind"] == "punch")
        rep["swaps"] += int(enter)
    return js, events, rep


def _feed(b):
    """Top-slot feeder pictures (feed.py) carry their own push/drift and hard-cut in: no deck camera, no swap."""
    return any(it.get("insert") in ("feed_item", "feed_card") for it in b.get("items") or [])


def caption_js(i, t):
    """Seam caption (split layout): the pill snaps in, 5 frames, small overshoot, no drift."""
    t = max(0.0, (round(t * FPS) - 0.5) / FPS)
    return (f"RRM.enter('pop',tl,'#c{i} .pill',{t:.5f},{{from:0.78,dur:0.2,blur:3}});")


CSS = """
.dcam{position:absolute;left:0;top:0;width:1080px;height:960px;transform-origin:540px 585px}
"""


def camera_at(rows, frame):
    """(s, x, y) of a deck camera on a frame (QA helper)."""
    s = (1.0, 0.0, 0.0)
    for r in rows:
        if r[0] > frame:
            break
        s = (r[1], r[2], r[3])
    return s

