"""Extra synthesized UI sounds for editorial-ui (ours, no samples), registered into stylekit sfx on import."""
import numpy as np

import sfx as _sfx


# ------------------------------------------------------------------ extra synthesized sounds (ours, no samples)
def _key():
    t = _sfx._t(0.05)
    x = _sfx._bandnoise(len(t), 2200, 9000) * np.exp(-t / 0.0045) + np.sin(2 * np.pi * 1700 * t) * np.exp(-t / 0.006) * 0.25
    return _sfx._stereo(x, 0.15)


def _shutter():
    t = _sfx._t(0.22)
    a = _sfx._bandnoise(len(t), 1200, 8000) * np.exp(-t / 0.006)
    t2 = np.clip(t - 0.085, 0, None)
    b = _sfx._bandnoise(len(t), 900, 6000) * np.exp(-t2 / 0.012) * (t >= 0.085) * 0.8
    thud = np.sin(2 * np.pi * 140 * t) * np.exp(-t / 0.03) * 0.35
    return _sfx._stereo(a + b + thud, 0.3)


def _tick():
    t = _sfx._t(0.06)
    x = np.sin(2 * np.pi * 3200 * t) * np.exp(-t / 0.008) + _sfx._bandnoise(len(t), 3000, 9000) * np.exp(-t / 0.002) * 0.3
    return _sfx._stereo(x, 0.05)


_sfx._MAKERS.setdefault("key", _key)
_sfx._MAKERS.setdefault("shutter", _shutter)
_sfx._MAKERS.setdefault("tick", _tick)
