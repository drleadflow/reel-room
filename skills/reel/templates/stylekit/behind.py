"""Bake a graded speaker video, optionally with text layers composited BEHIND the speaker (cutout matte).

  build_base(src, out, *, grade=None, layers=(), matte=None)

grade   dict for grade_lut(): gentle lift/warmth as a per-channel curve (no clipping, no grain)
layers  [{"png": RGBA 1080x1920 text layer, "f0": first frame, "f1": first frame after, "in": frames, "out": frames,
          "dy": px rise on entry, "s0": start scale}]
matte   VP9-alpha webm from cutout.py (same frame count). Refined per frame: temporal 1-2-1 smoothing (no edge
        flicker), 1 px erode (no halo), 1 px feather, then an edge-decontaminated composite:
            out = I + (1 - a_person) * (T_premult - a_text * B)
        where B is the wall behind the edge, estimated from confident background pixels around it, so the old wall
        colour never leaks into the hair/cap edge over the new text.
Frame count, fps and the audio track are preserved exactly (audio stream copied).
"""
import os
import subprocess

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30


def grade_lut(lift=0.02, gamma=0.94, knee=0.9, warm=0.015, sat=1.04, green=1.0):
    """Return a function img(uint8 RGB) -> graded uint8 RGB."""
    x = np.linspace(0, 1, 256)
    y = lift + (1 - lift) * np.power(x, gamma)
    hi = y > knee  # soft shoulder: never clip highlights
    y[hi] = knee + (1 - knee) * np.tanh((y[hi] - knee) / (1 - knee) * 1.0) * 0.985
    luts = []
    for ch, k in ((0, 1 + warm), (1, green), (2, 1 - warm)):
        luts.append(np.clip(np.round(np.clip(y * k, 0, 0.995) * 255), 0, 255).astype(np.uint8))

    def apply(img):
        out = np.stack([cv2.LUT(img[..., c], luts[c]) for c in range(3)], -1)
        if abs(sat - 1) > 1e-3:
            f = out.astype(np.float32)
            lum = f @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            f = lum[..., None] + (f - lum[..., None]) * sat
            out = np.clip(f, 0, 255).astype(np.uint8)
        return out
    return apply


def _reader(cmd, frame_bytes):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes * 2)
    while True:
        b = p.stdout.read(frame_bytes)
        if len(b) < frame_bytes:
            break
        yield b
    p.wait()


def frames_rgb(src):
    cmd = ["ffmpeg", "-v", "error", "-i", src, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    for b in _reader(cmd, W * H * 3):
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


def frames_alpha(matte):
    cmd = ["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", matte, "-vf", "alphaextract", "-f", "rawvideo",
           "-pix_fmt", "gray", "-"]
    for b in _reader(cmd, W * H):
        yield np.frombuffer(b, np.uint8).reshape(H, W)


def guided(I, p, r=8, eps=2e-4):
    """Colour guided filter (He et al.): snaps a soft matte's edges to the real edges of the image I (float RGB 0-1)."""
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))  # noqa: E731
    mI, mp = box(I), box(p)
    cov_Ip = box(I * p[..., None]) - mI * mp[..., None]
    S = np.empty(I.shape[:2] + (3, 3), np.float32)
    for i in range(3):
        for j in range(i, 3):
            v = box(I[..., i] * I[..., j]) - mI[..., i] * mI[..., j]
            S[..., i, j] = S[..., j, i] = v
    S += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(S, cov_Ip[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    return (box(a) * I).sum(-1) + box(b)


def clean_plate(src, matte, frames, roi, log=print):
    """Static-camera background plate inside rows roi=(y0,y1): per-pixel mean of the frames where the speaker is
    clearly NOT there (matte dilated 18 px). Returns (plate float RGB 0-1, valid mask) for difference refinement."""
    y0, y1 = roi
    want = set(frames)
    acc = np.zeros((y1 - y0, W, 3), np.float64)
    cnt = np.zeros((y1 - y0, W), np.float64)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    for f, (img, m) in enumerate(zip(frames_rgb(src), frames_alpha(matte))):
        if f > max(want):
            break
        if f not in want:
            continue
        free = cv2.dilate((m[y0:y1] > 10).astype(np.uint8), k) == 0
        acc[free] += img[y0:y1][free]
        cnt += free
    valid = cnt >= 3
    plate = (acc / np.maximum(cnt, 1)[..., None] / 255.0).astype(np.float32)
    # extend the plate ~24 px into never-seen pixels (inpaint) so edges right next to the speaker can be tested too
    ring = (cv2.dilate(valid.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (49, 49))) > 0) & ~valid
    if ring.any():
        filled = cv2.inpaint((plate * 255).astype(np.uint8), (~valid).astype(np.uint8), 9, cv2.INPAINT_TELEA)
        plate[ring] = filled[ring].astype(np.float32) / 255.0
        valid = valid | ring
    log(f"clean plate: rows {y0}-{y1}, {valid.mean() * 100:.0f}% of pixels seen without the speaker")
    return plate, valid


def _holes(hard):
    """Pixels enclosed by the person mask (not reachable from the top edge): holes to fill back in."""
    m = hard.astype(np.uint8)
    flood = m.copy()
    ff = np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8)
    for x in range(0, m.shape[1], 8):
        if flood[0, x] == 0:
            cv2.floodFill(flood, ff, (x, 0), 2)
    return (flood == 0)


def refine(prev, cur, nxt, erode_px=1, feather=1.0, img=None, roi=None, plate=None):
    a = (0.25 * prev + 0.5 * cur + 0.25 * nxt) / 255.0
    if img is not None:
        y0, y1 = roi if roi else (0, a.shape[0])
        I = img[y0:y1].astype(np.float32) / 255.0
        band = a[y0:y1].astype(np.float32)
        if plate is not None:
            pl, valid = plate[0][y0 - plate[2]:y1 - plate[2]], plate[1][y0 - plate[2]:y1 - plate[2]]
            d = np.sqrt(((I - pl) ** 2).mean(-1))
            looks_bg = np.clip((0.042 - d) / 0.02, 0, 1) * valid
            band = band * (1 - looks_bg)
            band = np.maximum(band, _holes(band > 0.5).astype(np.float32))  # never punch holes inside the person
        g = np.clip(guided(I, band, r=5, eps=6e-4), 0, 1)
        g = g * g * (3 - 2 * g)  # harden: hat and skin edges are crisp, the soft band was the matte's blur
        g = np.clip((g - 0.15) / 0.7, 0, 1)
        a = a.copy()
        a[y0:y1] = g
    if erode_px:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * erode_px + 1, 2 * erode_px + 1))
        a = cv2.erode(a, k)
    if feather:
        a = cv2.GaussianBlur(a, (0, 0), feather)
    return np.clip((a - 0.5) * 1.08 + 0.5, 0, 1).astype(np.float32)


def load_layer(png):
    im = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    if im is None or im.shape[2] != 4:
        raise SystemExit(f"text layer must be an RGBA png: {png}")
    rgba = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255.0
    a = rgba[..., 3:4]
    pm = rgba[..., :3] * a  # premultiplied
    return np.concatenate([pm, a], -1)


def ease_out(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def layer_at(layer, base, f):
    """Premultiplied RGBA of a layer at frame f (rise + scale + fade in, fade out), or None when hidden."""
    f0, f1 = layer["f0"], layer["f1"]
    if not (f0 <= f < f1):
        return None
    nin, nout = layer.get("in", 10), layer.get("out", 7)
    u = ease_out((f - f0 + 1) / nin)  # frame f0 already shows the layer partly in
    op = min(1.0, 0.25 + 0.75 * u)
    if f >= f1 - nout:
        op *= max(0.0, (f1 - f) / (nout + 1))
    dy = layer.get("dy", 40) * (1 - u)
    s = layer.get("s0", 1.05) + (1 - layer.get("s0", 1.05)) * u
    cx, cy = layer.get("cx", W / 2), layer.get("cy", H * 0.4)
    M = np.array([[s, 0, cx - s * cx], [0, s, cy - s * cy + dy]], np.float32)
    out = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    return out * op


def background_estimate(img, a_person):
    m = (a_person < 0.04).astype(np.float32)
    num = cv2.GaussianBlur(img * m[..., None], (0, 0), 7)
    den = cv2.GaussianBlur(m, (0, 0), 7)[..., None]
    est = num / np.maximum(den, 1e-3)
    return img * m[..., None] + est * (1 - m[..., None])


def composite(img_u8, a_person, layer_pm):
    img = img_u8.astype(np.float32) / 255.0
    ys, xs = np.nonzero(layer_pm[..., 3] > 0.002)
    if len(ys) == 0:
        return img_u8
    y0, y1 = max(0, ys.min() - 16), min(H, ys.max() + 17)
    x0, x1 = max(0, xs.min() - 16), min(W, xs.max() + 17)
    I = img[y0:y1, x0:x1]
    ap = a_person[y0:y1, x0:x1]
    T = layer_pm[y0:y1, x0:x1]
    B = background_estimate(I, ap)
    out = I + (1 - ap)[..., None] * (T[..., :3] - T[..., 3:4] * B)
    res = img_u8.copy()
    res[y0:y1, x0:x1] = np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
    return res


def build_base(src, out, *, grade=None, layers=(), matte=None, crf=13, plate_frames=None, log=print):
    layers = [dict(l, base=load_layer(l["png"])) for l in layers]
    need_matte = bool(layers)
    if need_matte and not (matte and os.path.exists(matte)):
        raise SystemExit("text behind the head needs the cutout matte (run cutout.py), or set the phrase to front")
    g = grade_lut(**grade) if grade else None
    tmp = out + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                            "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-colorspace", "bt709", tmp], stdin=subprocess.PIPE)
    mats = {}
    if need_matte:
        lo = min(l["f0"] for l in layers) - 1
        hi = max(l["f1"] for l in layers) + 1
        for f, m in enumerate(frames_alpha(matte)):
            if f > hi:
                break
            if f >= lo:
                mats[f] = m.astype(np.float32)
    plate = None
    if need_matte and plate_frames:
        y0 = max(0, min(int(l["cy"] - 300) for l in layers))
        y1 = min(H, max(int(l["cy"] + 360) for l in layers))
        pl, valid = clean_plate(src, matte, plate_frames, (y0, y1), log)
        plate = (pl, valid, y0, y1)
    n = 0
    for f, img in enumerate(frames_rgb(src)):
        img_raw = img
        if g:
            img = g(img)
        pm = None
        for l in layers:
            lp = layer_at(l, l["base"], f)
            if lp is not None:
                pm = lp if pm is None else lp + pm * (1 - lp[..., 3:4])
        if pm is not None:
            cur = mats[f]
            ys = np.nonzero(pm[..., 3].max(1) > 0.002)[0]
            roi = (max(0, ys.min() - 40), min(H, ys.max() + 41)) if len(ys) else None
            if plate is not None and roi:
                roi = (max(roi[0], plate[2]), min(roi[1], plate[3]))
            a = refine(mats.get(f - 1, cur), cur, mats.get(f + 1, cur), img=img_raw, roi=roi, plate=plate)
            img = composite(img, a, pm)
        enc.stdin.write(np.ascontiguousarray(img).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", src, "-map", "0:v", "-map", "1:a?", "-c", "copy",
                    "-movflags", "+faststart", out], check=True)
    os.remove(tmp)
    log(f"base video: {n} frames -> {out}")
    return n
