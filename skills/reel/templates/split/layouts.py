"""Speaker placement per layout, and the maths that maps a face in aroll pixels to where it lands on screen.

Layouts (per edl segment `mode`, or per project beat `layout`):
  split  top panel 0-960 (graphics), speaker below the seam, face centre `face_offset` px under the seam
  full   speaker full frame (as assembled); optional css punch-in `punch` (1.0-1.2) around the face;
         full-frame overlay items (titles, lists, cards) placed above the head box
  card   paper stage on top + the speaker inside a rounded card below (motion-editorial)
  stage  graphics only: paper stage, speaker hidden (his voice keeps running)
  media  full-frame media drawn by the beat (B-roll panels, a hook plate), speaker hidden; captions in a dark pill

Placement: {dx, dy, scale, ox, oy, visible, clip}. A point (x, y) of the aroll lands at
  ((x-ox)*scale+ox+dx, (y-oy)*scale+oy+dy).
"""

SEAM = 960
CARD_DEFAULT = {"top": 1010, "inset": 28, "radius": 64, "face_y": 1330, "scale": 1.0}


def card_cfg(pj):
    c = dict(CARD_DEFAULT)
    c.update((pj or {}).get("card", {}))
    return c


def _cover_shift(o, s, want, lo_edge, hi_edge, size):
    """Shift for a frame scaled by s about o so that `o` lands at `want` while the scaled frame [0, size] still covers
    [lo_edge, hi_edge] on screen (never exposes a frame edge)."""
    lo = hi_edge - o - (size - o) * s       # smallest shift: the far edge still reaches hi_edge
    hi = lo_edge + o * (s - 1)              # largest shift: the near edge still reaches lo_edge
    return round(max(lo, min(hi, want - o)))


def place(layout, fp, face_offset, card, punch=1.0, warn=None, target=None):
    """fp = facepos entry {cx, cy, h} (aroll px) or None.
    punch: extra zoom on `full` (around the face) and on `card` (multiplies card.scale; vary it on jump cuts).
    target: [x, y] screen point for the face centre on a punched `full` segment (edl "punch_at"); the frame is
    scaled about the face and shifted there, clamped so no frame edge ever shows."""
    if layout == "split":
        if fp:
            dy = round(min(max(SEAM + face_offset - fp["cy"], 0), SEAM))
        else:
            dy = 300
            if warn:
                warn("no facepos; using dy=300")
        return {"dy": dy, "scale": 1.0, "ox": 540, "oy": 0, "visible": True, "clip": None}
    if layout == "card":
        s = float(card.get("scale", 1.0)) * float(punch or 1.0)
        cy = fp["cy"] if fp else 990
        cxp = fp["cx"] if fp else 540
        if card.get("anchor"):   # a fixed, steady framing (a wide shot of speaker + board): ignore per-segment faces
            cxp, cy = card["anchor"]
        # face centre lands at card.face_y; scale about the face centre so the face stays put
        dy = round(card["face_y"] - cy)
        # centre the face horizontally, but never expose a frame edge inside the card (exact bounds for a face
        # off the frame centre: scaling happens about the face, not about x 540)
        dx = _cover_shift(cxp, s, 540, card["inset"], 1080 - card["inset"], 1080)
        return {"dy": dy, "dx": dx, "scale": round(s, 4), "ox": cxp, "oy": cy, "visible": True,
                "clip": f"inset({card['top']}px {card['inset']}px 0px {card['inset']}px round {card['radius']}px {card['radius']}px 0px 0px)"}
    if layout in ("stage", "media"):
        # stage: paper + graphics only. media: full-frame media (B-roll panels) drawn by the beat. Speaker hidden.
        return {"dy": 0, "scale": 1.0, "ox": 540, "oy": 0, "visible": False, "clip": None}
    # full
    if punch and abs(punch - 1.0) > 1e-3 and target and fp:
        s = float(punch)
        dx = _cover_shift(fp["cx"], s, target[0], 0, 1080, 1080)
        dy = _cover_shift(fp["cy"], s, target[1], 0, 1920, 1920)
        return {"dy": dy, "dx": dx, "scale": s, "ox": fp["cx"], "oy": fp["cy"], "visible": True, "clip": None}
    if punch and abs(punch - 1.0) > 1e-3:
        # origin well above the face: the head grows DOWNWARD, so the free band above it (titles, lists) keeps its room
        ox = fp["cx"] if fp else 540
        oy = (fp["cy"] - 2.0 * fp["h"]) if fp else 600
        return {"dy": 0, "scale": float(punch), "ox": ox, "oy": oy, "visible": True, "clip": None}
    return {"dy": 0, "scale": 1.0, "ox": 540, "oy": 0, "visible": True, "clip": None}


def map_pt(pl, x, y):
    s = pl["scale"]
    return (x - pl["ox"]) * s + pl["ox"] + pl.get("dx", 0), (y - pl["oy"]) * s + pl["oy"] + pl["dy"]


def face_box(pl, cx, cy, h, head_up=1.1, chin_down=0.8):
    """Screen-space boxes for one detection: skin box (brow..chin) and head box (cap/hair..chin)."""
    s = pl["scale"]
    X, Y = map_pt(pl, cx, cy)
    H = h * s
    skin = {"x": X - 0.5 * H, "y": Y - 0.55 * H, "w": H, "h": 1.35 * H}
    head = {"x": X - 0.65 * H, "y": Y - head_up * H, "w": 1.3 * H, "h": (head_up + chin_down) * H}
    return skin, head


def transform_css(pl):
    return {"x": pl.get("dx", 0), "y": pl["dy"], "scale": pl["scale"], "transformOrigin": f"{pl['ox']}px {pl['oy']}px"}
