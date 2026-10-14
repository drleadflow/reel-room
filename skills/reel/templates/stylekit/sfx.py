"""Soft UI sound effects, synthesized from scratch (no samples, nothing third-party). 48 kHz stereo float32.

make(name) -> (n,2) array normalised to peak 0.5; kit.mix_and_master sets the final level per cue relative to the voice.
Names: pop, pop_hi, pop_lo (card entrances), thump (word landing behind the head), chime (status / glow card),
click (one mouse click), swish (card sliding), whoosh (bigger move). LEAD[name] = seconds the sound starts before
its frame so the audible hit lands ON the frame (a swish peaks late, so it starts early).
"""
import numpy as np

SR = 48000
LEAD = {"swish": -0.16, "whoosh": -0.22, "thump": -0.01}
_rng = np.random.default_rng(7)


def _t(sec):
    return np.arange(int(sec * SR)) / SR


def _bandnoise(n, lo, hi):
    """Noise band-limited in the frequency domain (fast, no filters to design)."""
    spec = np.fft.rfft(_rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec *= ((f >= lo) & (f <= hi)) * np.exp(-((np.log(f + 1) - np.log((lo + hi) / 2)) ** 2) / 2.0)
    return np.fft.irfft(spec, n)


def _stereo(x, width=0.0):
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.5
    if width:
        d = int(width * SR / 1000)
        r = np.concatenate([np.zeros(d), x[:-d]]) if d else x
        return np.stack([x, r * 0.97], 1).astype(np.float32)
    return np.stack([x, x], 1).astype(np.float32)


def pop(f0=880.0, f1=430.0, dur=0.11):
    t = _t(dur)
    freq = f1 + (f0 - f1) * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(freq) / SR
    env = (1 - np.exp(-t / 0.0015)) * np.exp(-t / 0.032)
    body = np.sin(ph) * env
    click = _bandnoise(len(t), 1800, 6000) * np.exp(-t / 0.004) * 0.12
    return _stereo(body + click, 0.25)


def thump():
    t = _t(0.42)
    low = np.sin(2 * np.pi * (70 + 40 * np.exp(-t / 0.05)) * t) * np.exp(-t / 0.11)
    air = _bandnoise(len(t), 300, 3500) * np.exp(-((t - 0.05) / 0.06) ** 2) * 0.22
    return _stereo(low + air, 0.4)


def chime():
    t = _t(0.9)
    env = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.28)
    x = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1046.5, 1.0), (1568.0, 0.42), (2093.0, 0.16)))
    return _stereo(x * env, 0.6)


def click():
    t = _t(0.09)
    press = _bandnoise(len(t), 1500, 7000) * np.exp(-t / 0.0022)
    rel_t = np.clip(t - 0.055, 0, None)
    release = _bandnoise(len(t), 2500, 8000) * np.exp(-rel_t / 0.0016) * (t >= 0.055) * 0.55
    tick = np.sin(2 * np.pi * 2300 * t) * np.exp(-t / 0.003) * 0.3
    return _stereo(press + release + tick, 0.1)


def swish(dur=0.36):
    t = _t(dur)
    n = len(t)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2.2
    lo = _bandnoise(n, 250, 2500)
    hi = _bandnoise(n, 1500, 7000)
    mix = lo * (1 - t / dur) + hi * (t / dur) * 0.6
    return _stereo(mix * env, 0.8)


def whoosh():
    return swish(0.55)


_CACHE = {}
_MAKERS = {"pop": lambda: pop(), "pop_hi": lambda: pop(1100, 560, 0.1), "pop_lo": lambda: pop(700, 330, 0.12),
           "thump": thump, "chime": chime, "click": click, "swish": lambda: swish(), "whoosh": whoosh}


def make(name):
    if name not in _CACHE:
        if name not in _MAKERS:
            raise SystemExit(f"unknown sfx '{name}'. Known: {sorted(_MAKERS)}")
        _CACHE[name] = _MAKERS[name]()
    return _CACHE[name]
