#!/usr/bin/env python3
"""bake.py <project> [--matte-only] : the coloured set, baked frame by frame -> assets/base.mp4 (+ work/bake_qa.json)

Room cuts pass through untouched. Set cuts are rebuilt from four layers, back to front:
  1. plate     the set colour with a soft glow behind the head, a vignette and fine moving grain (premium, not flat)
  2. headline  serif lines from layers.py, each rising out of a mask on its first frames (BEHIND the speaker)
  3. contact   a soft shadow of the speaker on the plate and the type (so he sits in the set, not pasted on it)
  4. speaker   the person matte, refined:
                 - temporal 1-2-1 smoothing only where the picture is still (no flicker, no ghosting on fast hands)
                 - erode + feather (style.json set.edge) so no old-wall rim survives
                 - foreground colour estimation (blur-fusion: F from local colour statistics of the confident person and
                   background), so the edge pixels carry the person's colour, not the white wall's (no halo)
                 - a light wrap of the plate colour into the outermost edge, so the light matches
               then the set punch-in (zoom about the face centre) is applied to colour and alpha together.
Matte source per frame: work/matte/raw/fNNNNN.png (BiRefNet, matte_infer.py) when present, else assets/aroll_matte.webm.

Takeover cuts (Motion v2) pass the room through into base.mp4 and also write the refined speaker as a live cut-out,
assets/tko_<seg>.webm (VP9 + alpha, bt709, the cut's frames + 3 transparent ones for the renderer's coverage gate):
the HTML page sits between the two, so anything can animate behind the speaker.
"""
import json
import os
import subprocess
import sys
import time

import cv2
import numpy as np

import plan as _plan
import kit  # noqa: E402
import etheme as theme  # noqa: E402
import layers  # noqa: E402
from bake_fast import cutout_cache, fg_estimate_half, matte_key  # noqa: E402,F401  (opt-in speed paths)

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------- io
def reader(cmd, nbytes):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=nbytes * 2)
    try:
        while True:
            b = p.stdout.read(nbytes)
            if len(b) < nbytes:
                break
            yield b
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def _from(f0):
    """Filter prefix that starts decoding at frame f0 (frame exact; bake_par.py bakes spans in parallel)."""
    return f"select=gte(n\\,{f0}),setpts=N/FRAME_RATE/TB," if f0 else ""


def rgb_frames(video, f0=0):
    cmd = ["ffmpeg", "-v", "error", "-i", video, "-vf", _from(f0) + "scale=in_color_matrix=bt709:in_range=tv",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    for b in reader(cmd, W * H * 3):
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)


def alpha_frames(webm, f0=0):
    cmd = ["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", webm, "-vf", _from(f0) + "alphaextract", "-f", "rawvideo",
           "-pix_fmt", "gray", "-"]
    for b in reader(cmd, W * H):
        yield np.frombuffer(b, np.uint8).reshape(H, W)


# ----------------------------------------------------------------------------- matte refinement
def fg_estimate(img, a, radii=(90, 7)):
    """Blur-fusion foreground colour estimation (Forte & Pitie 2021, approximate fast version), own implementation."""
    a3 = a[..., None]
    F, B = img.copy(), img.copy()
    for r in radii:
        k = (2 * r + 1, 2 * r + 1)
        ba = cv2.blur(a, k)[..., None]
        bF = cv2.blur(F * a3, k) / (ba + 1e-5)
        bB = cv2.blur(B * (1 - a3), k) / ((1 - ba) + 1e-5)
        F = bF + a3 * (img - a3 * bF - (1 - a3) * bB)
        F = np.clip(F, 0, 1)
        B = bB
    return F


def refine_alpha(a, edge):
    """Tighten the soft rim, erode ~1 px, feather."""
    a = np.clip((a - 0.04) / 0.92, 0, 1)
    a = keep_body(a)
    e = float(edge.get("erode_px", 1.0))
    if e > 0:
        er = cv2.erode(a, np.ones((3, 3), np.uint8))
        a = a + (er - a) * min(e, 1.0)
    f = float(edge.get("feather_px", 0.8))
    if f > 0:
        a = cv2.GaussianBlur(a, (0, 0), f)
    return a


def keep_body(a, min_share=0.12):
    """Drop matte blobs that are not the speaker: keep the largest connected region (the body; hands and the mic are
    attached to it) plus any region at least `min_share` of its size, then soften the cut so edges stay intact."""
    m = (a > 0.35).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 2:
        return a
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = areas.max()
    keep = np.zeros(n, np.uint8)
    keep[1:] = (areas >= big * min_share).astype(np.uint8)
    mask = keep[lab]
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    return a * cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 3)


def temporal(prev, cur, nxt, gprev, gcur, gnxt):
    """1-2-1 alpha smoothing where the picture did not move (|diff| small); raw alpha where it moved."""
    if prev is None or nxt is None:
        return cur
    still = np.minimum(np.abs(gcur - gprev), np.abs(gcur - gnxt))
    w = np.clip(1.0 - still / 0.035, 0, 1)  # 1 = still, 0 = moving
    sm = 0.5 * cur + 0.25 * (prev + nxt)
    return cur + (sm - cur) * w


# ----------------------------------------------------------------------------- set layers
def plate_for(seg, sch, cfg, head_y):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.array(theme.hex_rgb(sch["plate"]), np.float32) / 255
    glow = np.array(theme.hex_rgb(sch["glow"]), np.float32) / 255
    edge = np.array(theme.hex_rgb(sch["edge"]), np.float32) / 255
    cx = seg["anchor"][0]
    d = np.sqrt(((xx - cx) / 760) ** 2 + ((yy - head_y) / 980) ** 2)
    g = np.exp(-(d ** 2) * 1.6)[..., None] * cfg["glow"]
    v = np.clip((np.sqrt(((xx - 540) / 720) ** 2 + ((yy - 980) / 1150) ** 2) - 0.55) / 0.75, 0, 1) ** 1.6
    v = (v * cfg["vignette"])[..., None]
    p = base * (1 - g) + glow * g
    return p * (1 - v) + edge * v


def warp(img, seg, interp=cv2.INTER_CUBIC):
    z = seg["zoom"]
    if abs(z - 1) < 1e-3:
        return img
    ax, ay = seg["anchor"]
    M = np.float32([[z, 0, ax * (1 - z)], [0, z, ay * (1 - z)]])
    return cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_REPLICATE)


class Headlines:
    """Per-frame RGBA of the active headline (masked rise on entry)."""

    def __init__(self, pl, tok, span=None):
        self.pl, self.items = pl, []
        hc = pl.cfg["headline"]
        self.rise = max(4, int(round(hc["rise_s"] * FPS)))
        for h in pl.headlines:
            if span and (h["f1"] <= span[0] - 1 or h["f0"] > span[1]):
                continue                     # a parallel span loads only its own layers (memory)
            r = layers.render_headline(pl, h, tok, layers.top_reserved(pl, h))
            if r.get("small"):
                pl.warn(f"headline {h['text']!r} hit the minimum size; shorten it or split it on '|'")
            lines = []
            for ln in r["lines"]:
                im = cv2.imread(ln["png"], cv2.IMREAD_UNCHANGED).astype(np.float32) / 255
                rgba = np.dstack([im[..., 2], im[..., 1], im[..., 0], im[..., 3]])  # BGRA -> RGBA
                lines.append({**ln, "rgba": rgba})
            self.items.append({**h, "lines": lines, "render": r})

    GHOST_F = 12            # frames for the previous headline to recede

    def full(self, h):
        """The whole headline (all lines settled), premultiplied RGBA."""
        if "_full" not in h:
            out = np.zeros((H, W, 4), np.float32)
            for ln in h["lines"]:
                a = ln["rgba"][..., 3:4]
                out[..., :3] = ln["rgba"][..., :3] * a + out[..., :3] * (1 - a)
                out[..., 3:4] = a + out[..., 3:4] * (1 - a)
            h["_full"] = out
        return h["_full"]

    def ghost(self, h, n):
        """Motion v2: when a headline replaces another in the same cut, the old one recedes behind it (smaller,
        higher, blurred, dim) and stays there as a ghost. Returns premultiplied RGBA or None."""
        prev = next((x for x in self.items if x["seg"] == h["seg"] and x["f1"] == h["f0"]), None)
        if prev is None or not self.pl.cfg["headline"].get("ghost", True):
            return None
        k = min((n - h["f0"] + 1) / self.GHOST_F, 1.0)
        if k >= 1 and "_ghost" in h:
            return h["_ghost"]
        e = 1 - (1 - k) ** 3
        src = self.full(prev)
        ys = [ln["y1"] for ln in prev["lines"]]
        cx, cy = 540.0, float(max(ys))
        sc = 1 - 0.4 * e
        M = np.float32([[sc, 0, cx * (1 - sc)], [0, sc, cy * (1 - sc) - 250 * e]])
        g = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        if e > 0.02:
            g = cv2.GaussianBlur(g, (0, 0), 0.5 + 13 * e)
        g *= (1 - 0.84 * e)
        if k >= 1:
            h["_ghost"] = g
        return g

    def at(self, n):
        h = next((x for x in self.items if x["f0"] <= n < x["f1"]), None)
        if not h:
            return None, None
        if h.get("_settled") is not None and n - h["f0"] > self.rise + 2 * len(h["lines"]) + self.GHOST_F:
            return h, h["_settled"]          # every line risen and the ghost gone: the layer no longer changes
        out = self._at(h, n)
        if n - h["f0"] > self.rise + 2 * len(h["lines"]) + self.GHOST_F:
            h["_settled"] = out
        return h, out

    def _at(self, h, n):
        out = np.zeros((H, W, 4), np.float32)
        gh = self.ghost(h, n)
        if gh is not None:      # premultiplied ghost under the new headline -> straight colour like the rest
            out[..., 3:4] = gh[..., 3:4]
            out[..., :3] = gh[..., :3] / np.maximum(gh[..., 3:4], 1e-4)
        for i, ln in enumerate(h["lines"]):
            k = (n - h["f0"] + 1) - 2 * (len(h["lines"]) - 1 - i) if not h["static"] else 10 ** 6
            if k <= 0:
                continue
            p = min(k / self.rise, 1.0)
            e = 1 - 2 ** (-10 * p) if p < 1 else 1.0
            dy = int(round((1 - e) * (ln["y1"] - ln["y0"]) * 1.06))
            src = ln["rgba"]
            if dy:
                src = np.zeros_like(src)
                src[dy:] = ln["rgba"][:-dy]
            # mask: nothing below the line's floor while rising (soft 14 px ramp under the ink box)
            if p < 1:
                floor = ln["y1"] + 10
                ramp = np.clip((floor + 14 - np.arange(H, dtype=np.float32)) / 14, 0, 1)[:, None]
                src = src * ramp[..., None]
            a = src[..., 3:4]
            out[..., :3] = src[..., :3] * a + out[..., :3] * (1 - a)
            out[..., 3:4] = a + out[..., 3:4] * (1 - a)
        return out


# ----------------------------------------------------------------------------- takeover cut-out (VP9 + alpha)
class CutoutWriter:
    """One VP9/alpha webm per takeover cut: straight (not premultiplied) colour, bt709, 3 transparent tail frames."""

    def __init__(self, path):
        self.path, self.tmp = path, path + ".part.webm"
        self.n = 0
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                                   "-r", str(FPS), "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuva420p",
                                   "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "20", "-row-mt", "1",
                                   "-deadline", "good", "-cpu-used", "3", "-auto-alt-ref", "0", "-g", "30",
                                   "-metadata:s:v:0", "alpha_mode=1", "-colorspace", "bt709", "-color_primaries", "bt709",
                                   "-color_trc", "bt709", "-color_range", "tv", "-f", "webm", self.tmp], stdin=subprocess.PIPE)

    def write(self, F, a):
        rgba = np.dstack([np.clip(F, 0, 1), np.clip(a, 0, 1)[..., None]])
        self.p.stdin.write((rgba * 255 + 0.5).astype(np.uint8).tobytes())
        self.n += 1

    def close(self, tail=3):
        z = np.zeros((H, W, 4), np.uint8).tobytes()
        for _ in range(tail):
            self.p.stdin.write(z)
        self.p.stdin.close()
        self.p.wait()
        if self.p.returncode:
            raise SystemExit(f"cut-out encode failed: {self.path}")
        os.replace(self.tmp, self.path)
        return self.n + tail


# ----------------------------------------------------------------------------- main
def _encoder(aroll, tmp, span):
    """x264 writer for the baked frames; a span (bake_par.py) is video only, the whole reel muxes the A-roll audio."""
    audio = [] if span else ["-i", aroll, "-map", "0:v", "-map", "1:a"]
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-"] + audio + (["-threads", "2"] if span else [])
                            + ["-c:v", "libx264", "-preset", "veryfast" if span else "medium", "-crf", "11",
                            "-g", "30", "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-pix_fmt", "yuv420p",
                            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-color_range", "tv"] + ([] if span else ["-c:a", "copy", "-movflags", "+faststart"])
                            + [tmp], stdin=subprocess.PIPE)


def bake(project, log=print, stills=None, span=None, out_path=None, qa_path=None):
    """stills: list of frame numbers -> PNGs in work/stills/ (no encode), for quick looks.
    span (f0, f1) + out_path + qa_path: bake only those frames into a video-only chunk (bake_par.py), cut-aligned."""
    pl = _plan.Plan(project)
    tok = theme.tokens(pl.proj.brand, pl.cfg)
    sc = pl.cfg["set"]
    aroll = pl.proj.p("assets", "aroll.mp4")
    raw_dir = pl.proj.p("work", "matte", "raw")
    webm = pl.proj.p("assets", "aroll_matte.webm")
    hl = Headlines(pl, tok, span)
    plates = {}

    def plate_key(s, key):
        if (s["id"], key) not in plates:
            head_y = (s["head_top"] + s["brow"]) / 2
            plates[(s["id"], key)] = plate_for(s, theme.scheme(tok, pl.cfg, key), sc, head_y)
        return plates[(s["id"], key)]

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    WIPE = 9

    def plate_at(s, n):
        """Motion v2: a colour switch on a word opens as a circle from behind the head (9 frames), not a hard flip."""
        key = pl.set_key_at(n)
        cur = plate_key(s, key)
        sw = next((h for h in pl.headlines if h["seg"] == s["id"] and 0 <= n - h["f0"] < WIPE and h["f0"] > s["f0"]), None)
        if not sw:
            return cur
        old_key = pl.set_key_at(sw["f0"] - 1)
        if old_key == key:
            return cur
        e = 1 - (1 - (n - sw["f0"] + 1) / WIPE) ** 3
        cx, cy = s["anchor"][0], (s["head_top"] + s["brow"]) / 2
        r = 2300 * e
        m = np.clip((r - np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)) / 28 + 0.5, 0, 1)[..., None]
        return plate_key(s, old_key) * (1 - m) + cur * m
    out = out_path or pl.proj.p("assets", "base.mp4")
    tmp = out + ".part.mp4"
    f_lo, f_hi = span or (0, pl.frames)
    class _Still:
        def __init__(self):
            self.n = 0
            self.stdin = self
            self.returncode = 0

        def write(self, b):
            if self.n in stills:
                os.makedirs(pl.proj.p("work", "stills"), exist_ok=True)
                im = np.frombuffer(b, np.uint8).reshape(H, W, 3)
                cv2.imwrite(pl.proj.p("work", "stills", f"s{self.n:05d}.png"), im[..., ::-1])
            self.n += 1

        def close(self):
            pass

        def wait(self):
            pass

    enc = _Still() if stills else _encoder(aroll, tmp, span)
    rng = np.random.default_rng(11 + f_lo)
    sources = {"birefnet": 0, "cutout": 0, "fallback": 0}
    cc = cutout_cache(pl)
    qa = {"frames": {}, "max_leak_px": 0}
    t0 = time.time()
    lo = max(0, f_lo - 1)                      # a span reads one frame of context on each side (temporal matte)
    frames = rgb_frames(aroll, lo)
    alphas = alpha_frames(webm, lo) if os.path.exists(webm) else None

    def load_alpha(n, fb, img=None):
        p = os.path.join(raw_dir, f"f{n:05d}.png")
        if os.path.exists(p):
            sources["birefnet"] += 1
            return cv2.imread(p, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
        a = cc[0].alpha(cc[1], n, img) if cc else None
        if a is not None:
            sources["cutout"] += 1
            return a
        sources["fallback"] += 1
        return (fb.astype(np.float32) / 255) if fb is not None else np.zeros((H, W), np.float32)

    cutouts, tko = {}, {}

    def emit(prev, cur, nxt):
        n, img, a_raw, g = cur
        s = pl.seg_of_frame(n)
        if s["scene"] not in ("set", "takeover"):
            enc.stdin.write(img.tobytes())
            return
        same = lambda x: x is not None and pl.seg_of_frame(x[0]) is s  # noqa: E731
        a = a_raw
        if sc["edge"].get("temporal", True) and same(prev) and same(nxt):
            a = temporal(prev[2], a_raw, nxt[2], prev[3], g, nxt[3])
        a = refine_alpha(a, sc["edge"])
        f = img.astype(np.float32) / 255
        F = (fg_estimate_half if sc["edge"].get("fg_half") else fg_estimate)(f, a)
        if s["scene"] == "takeover":
            enc.stdin.write(img.tobytes())          # the room stays under the page (seen while the circle opens)
            if stills:
                return
            if s["id"] not in tko:
                tko[s["id"]] = CutoutWriter(pl.proj.p("assets", f"tko_{s['id']}.webm"))
                page = theme.scheme(tok, pl.cfg, next((t["page"] for t in pl.takeovers if t["seg"] == s["id"]), "bone"))
                tko[s["id"] + ":page"] = np.array(theme.hex_rgb(page["plate"]), np.float32) / 255
            pg = tko[s["id"] + ":page"]
            wrap = float(sc["edge"].get("wrap", 0.2)) * 0.6 * np.clip((1 - a) * 2, 0, 1) * (a > 0.01)
            tko[s["id"]].write(F + (pg - F) * wrap[..., None], a)
            if n == s["f1"] - 1:
                cutouts[s["id"]] = tko.pop(s["id"]).close()
            return
        pla = plate_at(s, n)
        wrap = float(sc["edge"].get("wrap", 0.2)) * np.clip((1 - a) * 2, 0, 1) * (a > 0.01)
        F = F + (pla - F) * wrap[..., None]
        F, a = warp(F, s), np.clip(warp(a, s), 0, 1)
        under = pla.copy()
        h, layer = hl.at(n)
        if layer is not None:
            la = layer[..., 3:4]
            under = layer[..., :3] * la + under * (1 - la)
        gr = rng.standard_normal((H // 2, W // 2)).astype(np.float32)
        under = under + cv2.resize(gr, (W, H), interpolation=cv2.INTER_LINEAR)[..., None] * (sc["grain"] / 255)
        shp = sc["shadow"]
        sh = cv2.resize(cv2.GaussianBlur(cv2.resize(a, (W // 4, H // 4), interpolation=cv2.INTER_AREA), (0, 0), shp["blur"] / 4),
                        (W, H), interpolation=cv2.INTER_LINEAR)
        dy = int(shp["dy"])
        sh = np.vstack([np.zeros((dy, W), np.float32), sh[:-dy]]) if dy > 0 else sh
        op = shp["opacity"] * (0.75 if theme.scheme(tok, pl.cfg, pl.set_key_at(n))["light"] else 1.0)
        under = under * (1 - op * sh)[..., None]
        a3 = a[..., None]
        comp = F * a3 + under * (1 - a3)
        enc.stdin.write((np.clip(comp, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        if n % 3 == 0:
            fb = pl.face_box(n)
            if fb:
                # see-through holes: background-coloured pixels INSIDE the silhouette (not connected to the frame
                # border) within the face box. The headline sits behind the speaker, so a hole is the only way it
                # could ever show on the face.
                x0, y0, x1, y1 = [int(round(v)) for v in fb]
                x0, y0 = max(0, x0), max(0, y0)
                bg = (a < 0.5).astype(np.uint8)
                nl, lab = cv2.connectedComponents(bg, connectivity=4)
                border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
                enclosed = (bg > 0) & ~np.isin(lab, border)
                hole = int(enclosed[y0:y1, x0:x1].sum())
                leak = int(((layer[y0:y1, x0:x1, 3] > 0.15) & enclosed[y0:y1, x0:x1]).sum()) if layer is not None else 0
                core = a[y0:y1, x0:x1]
                qa["frames"][str(n)] = {"headline": h["id"] if h else None, "leak_px": leak, "core_holes": hole,
                                        "core_min_alpha": round(float(core.min()), 3) if core.size else None}
                qa["max_leak_px"] = max(qa["max_leak_px"], leak)
                qa["max_core_holes"] = max(qa.get("max_core_holes", 0), hole)

    prev = cur = None
    inside = lambda x: f_lo <= x[0] < f_hi  # noqa: E731
    for n, img in enumerate(frames, lo):
        if n > f_hi:
            break
        fb = next(alphas, None) if alphas is not None else None
        if pl.seg_of_frame(n)["scene"] in ("set", "takeover"):
            a = load_alpha(n, fb, img)
            g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255, (0, 0), 1.5)
        else:
            a, g = None, None
        item = (n, img, a, g)
        if stills and n > max(stills) + 1:
            break
        if cur is not None and inside(cur):
            emit(prev, cur, item)
        prev, cur = cur, item
        if n % 60 == 0:
            log(f"  bake {n}/{pl.frames}  {time.time() - t0:.0f}s")
    if cur is not None and inside(cur):
        emit(prev, cur, None)
    enc.stdin.close()
    enc.wait()
    if stills:
        log(f"stills: {pl.proj.p('work', 'stills')} (matte {sources})")
        return sources
    if enc.returncode:
        raise SystemExit("bake encode failed")
    got = kit.probe(tmp)["frames"]
    if got != f_hi - f_lo:
        raise SystemExit(f"bake wrote {got} frames, expected {f_hi - f_lo}")
    os.replace(tmp, out)
    for k, w in list(tko.items()):
        if isinstance(w, CutoutWriter):
            cutouts[k] = w.close()
    qa.update(sources=sources, seconds=round(time.time() - t0, 1), warnings=pl.warnings, cutouts=cutouts,
              headlines=[{"id": h["id"], "text": h["text"], "f0": h["f0"], "f1": h["f1"],
                          "lines": [{k: l[k] for k in ("x0", "y0", "x1", "y1", "px")} for l in h["lines"]]} for h in hl.items])
    kit.jsave(qa_path or pl.proj.p("work", "bake_qa.json"), qa)
    log(f"bake: {out} ({pl.frames} frames, matte birefnet={sources['birefnet']} fallback={sources['fallback']}, "
        f"max headline leak over face {qa['max_leak_px']} px, {qa['seconds']}s)")
    return qa


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    st = [int(x) for x in sys.argv[sys.argv.index("--stills") + 1].split(",")] if "--stills" in sys.argv else None
    bake(sys.argv[1], stills=st)
