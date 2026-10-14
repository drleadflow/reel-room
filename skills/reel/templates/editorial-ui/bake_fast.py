"""Speed paths for bake.py, all opt-in from project.json "editorial" (the plan compiler sets them):
  "matte": {"source": "cache"}     set-frame masks from the engine's per-frame cut-out cache (engine/cutout_cache.py)
  "set": {"edge": {"fg_half": true}} foreground colour estimation with half-resolution blur statistics
"""
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def fg_estimate_half(img, a, radii=(90, 7)):
    """fg_estimate with the blur statistics at half resolution (radii halved), the final colour solve at full size:
    the same edge colour (the blurred fields are smooth) for about a quarter of the memory traffic. Opt-in:
    "set": {"edge": {"fg_half": true}} (the plan compiler sets it for its time budget)."""
    h2, w2 = img.shape[0] // 2, img.shape[1] // 2
    i2 = cv2.resize(img, (w2, h2), interpolation=cv2.INTER_AREA)
    a2 = cv2.resize(a, (w2, h2), interpolation=cv2.INTER_AREA)
    a3 = a2[..., None]
    F, B = i2.copy(), i2.copy()
    for r in radii:
        k = (r + 1, r + 1)
        ba = cv2.blur(a2, k)[..., None]
        bF = cv2.blur(F * a3, k) / (ba + 1e-5)
        bB = cv2.blur(B * (1 - a3), k) / ((1 - ba) + 1e-5)
        F = np.clip(bF + a3 * (i2 - a3 * bF - (1 - a3) * bB), 0, 1)
        B = bB
    up = lambda x: cv2.resize(x, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)  # noqa: E731
    bF, bB, A = up(bF), up(bB), a[..., None]
    return np.clip(bF + A * (img - A * bF - (1 - A) * bB), 0, 1)


def cutout_cache(pl):
    """The engine's per-frame cut-out cache (engine/cutout_cache.py) when the plan asks for it ("matte":
    {"source": "cache"}, written by the plan compiler), else None."""
    if (pl.cfg.get("matte") or {}).get("source") != "cache":
        return None
    eng = os.path.join(os.path.dirname(os.path.dirname(HERE)), "engine")
    if eng not in sys.path:
        sys.path.append(eng)
    import cutout_cache as CC
    return CC, CC.cache_dir(pl.dir)


def matte_key(pl):
    """Bake-cache key part: which set frames have a cached cut-out mask."""
    cc = cutout_cache(pl)
    if not cc:
        return ""
    fr = [f for s in pl.segs if s["scene"] in ("set", "takeover") for f in range(s["f0"], s["f1"])]
    have = len(fr) if cc[0].waiting() else len(fr) - len(cc[0].missing(cc[1], fr))   # waiting: bake waits for all
    return f"cache:{have}/{len(fr)}"
