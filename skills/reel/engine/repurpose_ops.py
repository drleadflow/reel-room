"""Pixel operations for repurpose.py (no video IO here, so tests can call them on numpy frames).

Frames are BGR uint8 numpy arrays at SOURCE resolution. Every op returns a NEW frame and leaves pixels outside its box
untouched. Sizes scale with the frame width (reference: 720 px wide), so the same defaults work at 720p and 1080p.

Region schema: see repurpose.py. per_frame makes a region active ONLY on the listed frames, with x0/x1 replaced.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # the CLI turns this into a plain error with a fix line
    cv2 = None

REF_W = 720.0
METHODS = ("blur", "inpaint", "ref", "interp")


# ----------------------------------------------------------------------------- parsing
def hex_bgr(h, default="#121014"):
    h = (h or default).lstrip("#")
    if len(h) != 6:
        raise ValueError(f"fill colour must look like #1a1a1a, got {h!r}")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return np.array([b, g, r], np.float32)


def parse_range(spec, n):
    """'all' | None | [a,b] | 'a-b' | 'a' -> inclusive (a, b) clamped to 0..n-1"""
    if spec is None or spec == "all":
        return 0, n - 1
    if isinstance(spec, str):
        parts = spec.split("-")
        if not all(p.strip().isdigit() for p in parts) or len(parts) > 2:
            raise ValueError(f"frame range must look like 0-240 or 'all', got {spec!r}")
        spec = [int(parts[0]), int(parts[-1])]
    a, b = (spec, spec) if isinstance(spec, int) else (int(spec[0]), int(spec[1]))
    if a > b:
        raise ValueError(f"frame range starts after it ends: {spec}")
    return max(0, a), min(n - 1, b)


def scale_of(w):
    return w / REF_W


def grow_box(box, r):
    return [box[0] - r, box[1] - r, box[2] + r, box[3] + r]


def clip_box(box, w, h):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def region_box(region, i, n, w, h):
    """the box this region covers on frame i (pad applied, clipped), or None when it is not active"""
    a, b = parse_range(region.get("frames", "all"), n)
    if not a <= i <= b:
        return None
    x0, y0, x1, y1 = region["box"]
    if region.get("per_frame") is not None:
        ex = region["per_frame"].get(str(i))
        if not ex:
            return None
        x0, x1 = ex
    p = region.get("pad", 0)
    bx = clip_box((x0 - p, y0 - p, x1 + p, y1 + p), w, h)
    return bx if bx[2] > bx[0] and bx[3] > bx[1] else None


# ----------------------------------------------------------------------------- masks
def feather_mask(h, w, r):
    """1 deeper than r px from every edge, smooth ramp to 0 at the edge (h x w x 1 float32)"""
    r = max(1, int(r))
    dy = np.minimum(np.arange(h), np.arange(h)[::-1])[:, None]
    dx = np.minimum(np.arange(w), np.arange(w)[::-1])[None, :]
    t = np.clip((np.minimum(dx, dy).astype(np.float32) + 0.5) / r, 0, 1)
    return (t * t * (3 - 2 * t))[..., None]


def soft_window(box, r, w, h):
    """(grown box clipped to the frame, its feather mask). The ramp sits OUTSIDE box, so box itself is covered 100%;
    on a side where the box touches the frame edge there is no ramp."""
    x0, y0, x1, y1 = box
    m = feather_mask(y1 - y0 + 2 * r, x1 - x0 + 2 * r, r)
    gx0, gy0, gx1, gy1 = max(0, x0 - r), max(0, y0 - r), min(w, x1 + r), min(h, y1 + r)
    ox, oy = gx0 - (x0 - r), gy0 - (y0 - r)
    return (gx0, gy0, gx1, gy1), m[oy:oy + gy1 - gy0, ox:ox + gx1 - gx0]


def text_fill(img, colour=True):
    """bright text fill: white, yellow and (colour=True) saturated bright (pink/red titles)"""
    f = img.astype(np.int16)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    m = (b > 225) & (g > 225) & (r > 225)
    m |= (r > 200) & (g > 170) & (b < 130) & (r - b > 90)
    if colour:
        mx, mn = f.max(-1), f.min(-1)
        m |= (mx > 170) & (mx - mn > 70)
    return m.astype(np.uint8)


def thin_text(img, colour=True, pill=False):
    """glyph pixels: bright fill in THIN strokes (big bright areas like a white chair are removed by an opening) with a
    dark stroke or background close by. pill=True also accepts text with no stroke on a mid-tone pill or box (the
    stroke is clearly brighter than its surroundings: a white top-hat)."""
    s = scale_of(img.shape[1])
    fill = text_fill(img, colour)
    k = max(5, int(round(9 * s)) | 1)
    big = cv2.morphologyEx(fill, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    dark = (img.max(-1) < 55).astype(np.uint8)
    r = max(2, int(round(3 * s)))
    near = cv2.dilate(dark, np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    if pill:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k + 4, k + 4)))
        near = near | (th > 50).astype(np.uint8)
    return fill & (1 - big) & near


def text_like(img, colour=True):
    """bool mask: bright text fill or thin glyph strokes"""
    return (text_fill(img, colour) | thin_text(img, colour)).astype(bool)


def glyph_mask(frames, box, thresh=0.85, colour=True, grow=None, solid=True):
    """static glyph mask (full-frame uint8 0/255) inside box: text fill present in > thresh of the frames where the
    text shows at all (fades are skipped), plus its static dark outline and drop shadow, dilated a little"""
    h, w = frames[0].shape[:2]
    s = scale_of(w)
    reach = max(3, int(round(12 * s)) | 1)
    x0, y0, x1, y1 = clip_box(grow_box(box, reach), w, h)
    subs = [f[y0:y1, x0:x1] for f in frames]
    fills = [text_like(sb, colour) for sb in subs]
    counts = np.array([m.sum() for m in fills], np.float64)
    on = [j for j, c in enumerate(counts) if c > 0.3 * counts.max()] if counts.max() > 0 else []
    if not on:
        return np.zeros((h, w), np.uint8)
    fill = np.mean([fills[j] for j in on], axis=0) > thresh
    dark = np.mean([subs[j].max(-1) < 45 for j in on], axis=0) > thresh
    near = cv2.dilate(fill.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (reach, reach)))
    core = (fill | (dark & (near > 0))).astype(np.uint8) * 255
    g = grow or max(3, int(round(7 * s)) | 1)
    core = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (g, g)))
    if solid:  # letters merged into word blocks: an inpaint shaped like letters reads as ghost text
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(30 * s)) | 1, max(3, int(15 * s)) | 1))
        core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, k)
    m = np.zeros((h, w), np.uint8)
    m[y0:y1, x0:x1] = core
    return m


# ----------------------------------------------------------------------------- methods
def op_blur(img, box, sigma=None, tint=0.4, fill=None, feather=None):
    """heavy blur + tint toward fill: box fully covered, feathered over `feather` px outside it"""
    h, w = img.shape[:2]
    s = scale_of(w)
    (x0, y0, x1, y1), m = soft_window(box, int(feather or 18 * s), w, h)
    sigma = float(sigma or 30 * s)
    pad = int(sigma * 3)
    a0, b0 = max(0, y0 - pad), max(0, x0 - pad)
    big = img[a0:min(h, y1 + pad), b0:min(w, x1 + pad)].astype(np.float32)
    sm = cv2.resize(big, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    sm = cv2.GaussianBlur(sm, (0, 0), max(1.0, sigma / 4))
    bl = cv2.resize(sm, (big.shape[1], big.shape[0]), interpolation=cv2.INTER_LINEAR)
    bl = bl[y0 - a0:y1 - a0, x0 - b0:x1 - b0]
    bl = bl * (1 - tint) + hex_bgr(fill) * tint
    out = img.copy()
    reg = img[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(reg * (1 - m) + bl * m, 0, 255).astype(np.uint8)
    return out


def _grain(shape, seed, amount):
    return np.random.default_rng(int(seed)).normal(0, amount, shape).astype(np.float32)


def op_inpaint(img, box, mask=None, seed=0, grain=2.0):
    """cv2 TELEA over the mask (or the whole box) + soft blend + light seeded grain"""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    s = scale_of(w)
    if mask is None:
        m = np.zeros((h, w), np.uint8)
        m[y0:y1, x0:x1] = 255
    else:  # a glyph mask may reach a few px past the box (outline, shadow)
        m = mask
        ys, xs = np.nonzero(m)
        if not len(ys):
            return img.copy()
        x0, y0, x1, y1 = min(x0, xs.min()), min(y0, ys.min()), max(x1, xs.max() + 1), max(y1, ys.max() + 1)
    mg = int(24 * s) + 8
    a0, b0, a1, b1 = max(0, y0 - mg), max(0, x0 - mg), min(h, y1 + mg), min(w, x1 + mg)
    sub, sm = img[a0:a1, b0:b1], m[a0:a1, b0:b1]
    ip = cv2.inpaint(sub, sm, max(3, int(6 * s)), cv2.INPAINT_TELEA)
    ip = cv2.GaussianBlur(ip, (0, 0), 3.0 * s + 0.5).astype(np.float32)
    soft = cv2.GaussianBlur(sm.astype(np.float32) / 255, (0, 0), 5.0 * s + 0.5)
    soft = np.maximum(soft, (sm > 0).astype(np.float32))[..., None]
    ip += _grain(ip.shape, seed, grain) * soft
    out = img.copy()
    out[a0:a1, b0:b1] = np.clip(sub * (1 - soft) + ip * soft, 0, 255).astype(np.uint8)
    return out


def op_ref(img, box, ref, mask=None, feather=None):
    """fill box (or the glyph mask inside it) from a clean reference image (median of clean frames), feathered"""
    h, w = img.shape[:2]
    s = scale_of(w)
    r = int(feather or 8 * s)
    x0, y0, x1, y1 = box
    if mask is None:
        (x0, y0, x1, y1), m = soft_window(box, r, w, h)
    else:
        ys, xs = np.nonzero(mask)
        if not len(ys):
            return img.copy()
        x0, y0, x1, y1 = clip_box((min(x0, xs.min()) - r, min(y0, ys.min()) - r, max(x1, xs.max() + 1) + r,
                                   max(y1, ys.max() + 1) + r), w, h)
        big = cv2.dilate(mask[y0:y1, x0:x1], cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        m = cv2.GaussianBlur(big.astype(np.float32) / 255, (0, 0), r / 2)
        m = np.maximum(m, (mask[y0:y1, x0:x1] > 0).astype(np.float32))[..., None]
    out = img.copy()
    reg = img[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(reg * (1 - m) + ref[y0:y1, x0:x1].astype(np.float32) * m, 0, 255).astype(np.uint8)
    return out


def op_interp(img, box, seed=0, noise=1.6, feather=None):
    """column-wise interpolation between the rows just above and just below box + seeded noise (flat walls)"""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    s = scale_of(w)
    k = max(2, int(5 * s))
    above = img[max(0, y0 - k):y0, x0:x1].astype(np.float32)
    below = img[y1:min(h, y1 + k), x0:x1].astype(np.float32)
    if not above.size and not below.size:
        return op_blur(img, box)
    top = above.mean(0) if above.size else below.mean(0)
    bot = below.mean(0) if below.size else top
    top, bot = (cv2.GaussianBlur(v[None], (0, 0), 2)[0] for v in (top, bot))
    t = np.linspace(0, 1, y1 - y0, dtype=np.float32)[:, None, None]
    fill = top[None] * (1 - t) + bot[None] * t + _grain((y1 - y0, x1 - x0, 3), seed, noise)
    r, xs = max(1e-6, float(feather or 0)), np.arange(x1 - x0)
    m = np.clip(np.minimum(xs, xs[::-1]) / r, 0, 1).astype(np.float32)[None, :, None] if feather else 1.0
    out = img.copy()
    reg = img[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(reg * (1 - m) + fill * m, 0, 255).astype(np.uint8)
    return out


def apply_region(img, region, i, n, ctx=None):
    """apply one region to frame i; ctx = {"mask": full-frame glyph mask, "ref": clean reference image}"""
    h, w = img.shape[:2]
    box = region_box(region, i, n, w, h)
    if box is None:
        return img
    ctx = ctx or {}
    meth = region.get("method", "blur")
    if meth == "blur":
        return op_blur(img, box, region.get("sigma"), region.get("tint", 0.4), region.get("fill"), region.get("feather"))
    if meth == "inpaint":
        return op_inpaint(img, box, ctx.get("mask"), seed=i, grain=region.get("grain", 2.0))
    if meth == "ref":
        if ctx.get("ref") is None:
            raise ValueError(f"region {region.get('id')}: method ref needs ref_frames [a,b] of clean frames")
        return op_ref(img, box, ctx["ref"], ctx.get("mask"), region.get("feather"))
    if meth == "interp":
        return op_interp(img, box, seed=i, noise=region.get("noise", 1.6), feather=region.get("feather"))
    raise ValueError(f"region {region.get('id')}: unknown method {meth!r} (use one of {', '.join(METHODS)})")


# ----------------------------------------------------------------------------- detection helpers
def caption_extent(img, y0, y1, min_px=None):
    """horizontal extent [x0, x1] of caption glyphs (white/yellow fill with a dark stroke) in rows y0..y1, or None.
    Columns are grouped into clusters split by gaps wider than 5% of the width; the cluster with most pixels wins."""
    w = img.shape[1]
    s = scale_of(w)
    m = thin_text(img[y0:y1], colour=False)
    cols = m.sum(0)
    if cols.sum() < (min_px or 40 * s * s):
        return None
    xs = np.nonzero(cols)[0]
    gap = 0.05 * w
    splits = np.nonzero(np.diff(xs) > gap)[0]
    groups = np.split(xs, splits + 1)
    best = max(groups, key=lambda g: cols[g].sum())
    if cols[best].sum() < (min_px or 40 * s * s):
        return None
    return [int(best[0]), int(best[-1]) + 1]


def find_band(row_counts, h, lo=0.40, hi=0.85, frac=0.2):
    """caption band [y0, y1] from summed per-row glyph counts (len == h): the run around the peak row inside lo..hi"""
    r = np.convolve(np.asarray(row_counts, np.float64), np.ones(5) / 5, mode="same")
    a, b = int(lo * h), int(hi * h)
    if b <= a or r[a:b].max() <= 0:
        return None
    pk = a + int(np.argmax(r[a:b]))
    thr = r[pk] * frac
    y0, y1 = pk, pk
    while y0 > a and r[y0 - 1] > thr:
        y0 -= 1
    while y1 < b - 1 and r[y1 + 1] > thr:
        y1 += 1
    p = int(0.008 * h) + 2
    return [max(0, y0 - p), min(h, y1 + 1 + p)]


def iou(a, b):
    uni = np.logical_or(a, b).sum()
    return np.logical_and(a, b).sum() / uni if uni else 0.0


def static_windows(samples, step, thresh=0.85, min_len=3, split_iou=0.3):
    """samples: [(frame, bool mask)] in order. Groups consecutive samples whose masks agree into windows, keeps pixels
    present in > thresh of a window. Returns [(f0, f1, static_mask)]."""
    out, cur = [], []

    def close():
        if len(cur) >= min_len:
            st = np.mean([m for _, m in cur], axis=0) > thresh
            if st.sum() > 0:
                out.append((cur[0][0], cur[-1][0] + step - 1, st))

    for f, m in samples:
        if cur:
            cons = np.mean([c for _, c in cur[-8:]], axis=0) > 0.5
            if (cons.sum() or m.sum()) and iou(cons, m) < split_iou:
                close()
                cur = []
        cur.append((f, m))
    close()
    return out


def blobs(mask, merge, min_area):
    """bounding boxes [x0,y0,x1,y1] of mask blobs after merging pieces closer than merge px"""
    k = max(1, int(merge)) | 1
    m = cv2.dilate(mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (k, max(1, k // 2) | 1)))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    out = []
    for j in range(1, n):
        x, y, bw, bh, _ = st[j]
        sub = mask[y:y + bh, x:x + bw]
        if sub.sum() >= min_area:
            ys, xs = np.nonzero(sub)
            out.append([int(x + xs.min()), int(y + ys.min()), int(x + xs.max() + 1), int(y + ys.max() + 1)])
    return out


def text_span(text, lx0, lx1):
    """column extent of the text clusters (split at gaps > 5% width) that touch lx0..lx1"""
    cols = np.nonzero(text.sum(0) > 0)[0]
    if not len(cols):
        return lx0, lx1
    groups = np.split(cols, np.nonzero(np.diff(cols) > 0.05 * text.shape[1])[0] + 1)
    keep = [gr for gr in groups if gr[-1] >= lx0 and gr[0] <= lx1] or [np.array([lx0, lx1 - 1])]
    return min(int(gr[0]) for gr in keep), max(int(gr[-1]) for gr in keep) + 1


def card_sides(g, y0, y1, tx0, tx1):
    """left/right card edges: the nearest long vertical edges (> 60% of the card height) outside the text extent"""
    w = g.shape[1]
    gx = np.abs(cv2.Sobel(g[y0:y1], cv2.CV_16S, 1, 0, ksize=3))
    cols = (gx > 50).sum(0) > 0.6 * (y1 - y0)
    left, right, m = np.nonzero(cols[:tx0])[0], np.nonzero(cols[tx1:])[0] + tx1, int(0.04 * w)
    return (int(left[-1]) if len(left) else max(0, tx0 - m)), (int(right[0]) + 1 if len(right) else min(w, tx1 + m))


def card_bottom(g, y_text, x0, x1, y_stop):
    """card bottom: the first long-ish horizontal edge (>= 25% of the card width) below the last text row, else a
    generous margin. Cards are often translucent, so the fill itself is not reliable."""
    h = g.shape[0]
    lo, hi = max(0, y_text - int(0.01 * h)), min(y_stop, y_text + int(0.1 * h))
    if hi - lo < 3:
        return min(y_stop, y_text)
    gy = np.abs(cv2.Sobel(g[lo:hi, x0:x1], cv2.CV_16S, 0, 1, ksize=3))
    k = max(3, int(0.25 * (x1 - x0)))
    ln = cv2.morphologyEx((gy > 25).astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    rows = np.nonzero(ln.any(1))[0]
    if len(rows):
        return min(y_stop, lo + int(rows[-1] if rows[-1] - rows[0] < 6 else rows[0]) + 3)
    return min(y_stop, y_text + int(0.05 * h))


def card_candidates(img, y_stop=None):
    """flat card boxes on one frame: a long horizontal edge (the card top) with text glyphs below it, on a dark or
    light flat fill. Sides = nearest long vertical edges; bottom = last text row + a margin (check it on the sheet)."""
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gy = np.abs(cv2.Sobel(g, cv2.CV_16S, 0, 1, ksize=3))
    lines = cv2.morphologyEx((gy > 60).astype(np.uint8), cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (int(0.35 * w), 1)))
    a, b = int(0.15 * h), int(y_stop or 0.9 * h)
    text = thin_text(img)
    out, used = [], -1
    for y in np.nonzero(lines[a:b].any(1))[0] + a:
        if y <= used:
            continue
        xs = np.nonzero(lines[y])[0]
        lx0, lx1 = int(xs.min()), int(xs.max()) + 1
        sub = text[y + 3:min(b, y + int(0.4 * h)), lx0:lx1]
        rows = np.nonzero(sub.sum(1) > 2)[0]
        if len(rows) < 4 or rows[0] > 0.15 * h:
            continue
        gaps = np.nonzero(np.diff(rows) > 0.06 * h)[0]
        last = rows[gaps[0]] if len(gaps) else rows[-1]
        y1 = min(b, int(y + 3 + last + 0.01 * h))
        if 80 < float(g[y:y1, lx0:lx1].mean()) < 175:
            continue
        tx0, tx1 = text_span(text[y + 3:y1], lx0, lx1)
        x0, x1 = card_sides(g, int(y), y1, tx0, tx1)
        x0, x1 = min(x0, lx0), max(x1, lx1)
        y1 = card_bottom(g, y1, x0, x1, b)
        out.append([x0, int(y), x1, y1])
        used = y1
    return out


def track_boxes(samples, step, min_len=3, link=0.5):
    """samples: [(frame, [boxes])]. Links boxes that overlap (IoU > link) across consecutive samples into tracks.
    Returns [(f0, f1, median box)] for tracks seen in >= min_len samples."""
    def biou(p, q):
        ix = max(0, min(p[2], q[2]) - max(p[0], q[0]))
        iy = max(0, min(p[3], q[3]) - max(p[1], q[1]))
        u = (p[2] - p[0]) * (p[3] - p[1]) + (q[2] - q[0]) * (q[3] - q[1]) - ix * iy
        return ix * iy / u if u else 0.0

    live, done = [], []
    for f, boxes in samples:
        nxt = []
        for bx in boxes:
            t = next((t for t in live if biou(t["all"][-1], bx) > link), None)
            live = [x for x in live if x is not t]
            t = t or {"f0": f, "all": []}
            t["all"].append(list(bx))
            t["f1"] = f + step - 1
            nxt.append(t)
        done += live
        live = nxt
    done += live
    keep = [t for t in sorted(done, key=lambda t: t["f0"]) if len(t["all"]) >= min_len]
    return [(t["f0"], t["f1"], [int(v) for v in np.median(np.array(t["all"]), axis=0)]) for t in keep]


def pill_box(img, box, tol=18):
    """box of a flat pill or panel behind title text, or None. The pill = pixels of the colour just around the glyphs,
    connected to them; rejected when that colour floods far past the text (it is the wall, not a pill)."""
    (h, w), s = img.shape[:2], scale_of(img.shape[1])
    gx0, gy0, gx1, gy1 = clip_box(grow_box(box, int(40 * s)), w, h)
    sub = img[gy0:gy1, gx0:gx1]
    gl = cv2.dilate(text_like(sub).astype(np.uint8), np.ones((5, 5), np.uint8))
    ring = (cv2.dilate(gl, np.ones((15, 15), np.uint8)) > 0) & (gl == 0)
    if not ring.any():
        return None
    col = np.median(sub[ring], axis=0)
    near = (np.abs(sub.astype(np.int16) - col).max(-1) < tol) | (gl > 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats(near.astype(np.uint8))
    j = np.bincount(lab[ring], minlength=n)[1:].argmax() + 1
    x, y, bw, bh = (int(v) for v in st[j][:4])
    ys, xs = np.nonzero(gl)
    edge = x == 0 or y == 0 or x + bw >= sub.shape[1] or y + bh >= sub.shape[0]
    inside = x <= xs.min() + 2 and y <= ys.min() + 2 and x + bw >= xs.max() - 2 and y + bh >= ys.max() - 2
    if edge or not inside or bw * bh > 3 * (box[2] - box[0]) * (box[3] - box[1]):
        return None  # floods to the search edge or far past the text: that colour is the background
    return grow_box([gx0 + x, gy0 + y, gx0 + x + bw, gy0 + y + bh], max(2, int(3 * s)))


# ----------------------------------------------------------------------------- crop (hide by layout)
def crop_plan(src_w, src_h, regions, out_w=1080, out_h=1920, cx=0.5):
    """largest out_w:out_h crop that keeps the bands (kind title/caption, or "exclude": true) outside it: a band in the
    top third pushes the crop down, one in the bottom third pushes it up. Bands in the middle third and other regions
    (cards) cannot be cropped away and are returned in "uncovered" (cover those with bake). Returns crop box, zoom/cx/cy for
    edl.json (assemble.crop_box semantics) and the upscale factor."""
    top, bot, left_over = 0.0, float(src_h), []
    for r in regions:
        x0, y0, x1, y1 = r["box"]
        mid, band = (y0 + y1) / 2, r.get("exclude", r.get("kind", "title") in ("title", "caption"))
        if band and mid < src_h / 3:
            top = max(top, y1)
        elif band and mid > src_h * 2 / 3:
            bot = min(bot, y0)
        else:
            left_over.append(r.get("id"))
    if bot - top < 0.25 * src_h:
        raise ValueError("the bands leave less than a quarter of the frame; hide them by covering (bake) instead")
    ar, ch = out_w / out_h, bot - top
    cw = ch * ar
    if cw > src_w:
        cw, ch = float(src_w), src_w / ar
    y = top + ((bot - top) - ch) / 2
    x = min(max(cx * src_w - cw / 2, 0), src_w - cw)
    bw, bh = (src_h * ar, src_h) if src_w / src_h > ar else (src_w, src_w / ar)
    return {"box": [round(x), round(y), round(x + cw), round(y + ch)], "w": round(cw), "h": round(ch),
            "zoom": round(bh / ch, 4), "cx": round((x + cw / 2) / src_w, 4), "cy": round((y + ch / 2) / src_h, 4),
            "upscale": round(out_h / ch, 3), "uncovered": left_over}
