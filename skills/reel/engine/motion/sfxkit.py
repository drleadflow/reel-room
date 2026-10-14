"""sfxkit: Reel Room's own sound-effect kit, synthesized from scratch with numpy (no samples, no downloads).

Every sound is built from filtered noise, sines and envelopes with fixed seeds, so a run always writes the same
samples. Files are cached as 48 kHz stereo 24-bit WAVs in ~/.reel-room/cache/sfx/<KIT_VERSION>/ with a sidecar
JSON per sound: length, peak offset (start of the loudest 10 ms window + 5 ms, i.e. where the hit lands) and the
max momentary loudness (LUFS, 400 ms) measured once with ffmpeg ebur128.

The mixer starts a sound at `event_time - peak` so its loudest moment lands ON the visual event.

Sounds (soft by design: testers found dense, bright SFX annoying; these sit under a voice):
  whoosh        air pass-by, mid band sweeping up then down, light stereo travel     whip / card cut
  whoosh_soft   lighter, airy, shorter                                                  push / back to speaker
  whoosh_deep   low air plus a sinking sub                                              zoom-through / drop
  swish         very short high air                                                     iris / wipe / slide
  pop           round bubble blip                                                       a tile or pill lands
  tick          tiny bright tick                                                        a counter step, a check
  click         soft UI click with a faint second tap                                   a button, a text box
  stamp         short low thump with a paper slap                                       a stamped word
  impact        short sub hit with a soft crack                                         smash cut, a big number
  riser         0.9 s rising air + tone that peaks at its end                           into a hit or a reveal
  shutter       two-stage camera shutter                                                a screenshot, a flash
"""
import json
import os
import subprocess

SR = 48000
KIT_VERSION = "v1"
HOME = os.environ.get("REEL_ROOM_HOME") or os.path.expanduser("~/.reel-room")
CACHE = os.path.join(HOME, "cache", "sfx", KIT_VERSION)
NAMES = ("whoosh", "whoosh_soft", "whoosh_deep", "swish", "pop", "tick", "click", "stamp", "impact", "riser", "shutter")


def _np():
    import numpy as np
    return np


def _t(n):
    return _np().arange(n) / SR


def _band_noise(n, centers, width, seed):
    """Noise through a time-varying gaussian band (STFT shaping). centers: array of centre Hz per output sample."""
    np = _np()
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n + 2048)
    win, hop = 1024, 256
    w = np.hanning(win)
    out = np.zeros(n + 2048)
    norm = np.zeros(n + 2048)
    fr = np.fft.rfftfreq(win, 1 / SR)
    for s in range(0, n, hop):
        seg = x[s:s + win]
        if len(seg) < win:
            break
        c = float(centers[min(s + win // 2, n - 1)])
        bw = max(80.0, c * width)
        sp = np.fft.rfft(seg * w) * np.exp(-((fr - c) / bw) ** 2)
        out[s:s + win] += np.fft.irfft(sp, win) * w
        norm[s:s + win] += w * w
    out = out[:n] / np.maximum(norm[:n], 1e-3)
    return out


def _lowpass(x, hz):
    np = _np()
    sp = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    sp *= 1 / np.sqrt(1 + (fr / hz) ** 4)
    return np.fft.irfft(sp, len(x))


def _sweep(n, f0, f1, curve=1.0):
    np = _np()
    p = np.linspace(0, 1, n) ** curve
    f = f0 + (f1 - f0) * p
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _env_gauss(n, peak_at, width):
    np = _np()
    t = np.linspace(0, 1, n)
    return np.exp(-((t - peak_at) / width) ** 2)


def _decay(n, attack, tau):
    np = _np()
    t = _t(n)
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-np.maximum(0, t - attack) / tau)


def _stereo(x, pan_from=0.0, pan_to=0.0):
    """Equal-power pan moving from pan_from to pan_to (-1 left .. 1 right)."""
    np = _np()
    p = np.linspace(pan_from, pan_to, len(x))
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def build(name):
    """Synthesize one sound -> float32 (n, 2), peak normalised to -3 dBFS, 2 ms fade in / 8 ms fade out."""
    np = _np()
    if name == "whoosh":
        n = int(0.55 * SR)
        p = np.linspace(0, 1, n)
        c = 420 + 1900 * np.exp(-((p - 0.6) / 0.25) ** 2)
        x = _band_noise(n, c, 0.75, 11) * _env_gauss(n, 0.6, 0.26)
        y = _stereo(x, -0.35, 0.35)
    elif name == "whoosh_soft":
        n = int(0.42 * SR)
        p = np.linspace(0, 1, n)
        c = 1300 + 1500 * np.exp(-((p - 0.55) / 0.3) ** 2)
        x = _band_noise(n, c, 0.9, 12) * _env_gauss(n, 0.55, 0.28)
        y = _stereo(x, 0.3, -0.3)
    elif name == "whoosh_deep":
        n = int(0.7 * SR)
        p = np.linspace(0, 1, n)
        c = 180 + 700 * np.exp(-((p - 0.55) / 0.25) ** 2)
        air = _band_noise(n, c, 0.8, 13) * _env_gauss(n, 0.55, 0.25)
        sub = _sweep(n, 70, 38, 1.4) * _env_gauss(n, 0.6, 0.3) * 0.45
        y = _stereo(air + sub)
    elif name == "swish":
        n = int(0.24 * SR)
        p = np.linspace(0, 1, n)
        c = 2600 + 2400 * p
        x = _band_noise(n, c, 0.6, 14) * _env_gauss(n, 0.45, 0.3)
        y = _stereo(x, -0.2, 0.2)
    elif name == "pop":
        n = int(0.11 * SR)
        x = _sweep(n, 520, 1050, 0.5) * _decay(n, 0.002, 0.026)
        x += _lowpass(np.random.default_rng(15).standard_normal(n), 3000) * _decay(n, 0.0005, 0.004) * 0.25
        y = _stereo(x)
    elif name == "tick":
        n = int(0.05 * SR)
        t = _t(n)
        x = np.sin(2 * np.pi * 2900 * t) * _decay(n, 0.0004, 0.007)
        x += _lowpass(np.random.default_rng(16).standard_normal(n), 7000) * _decay(n, 0.0003, 0.002) * 0.35
        y = _stereo(x)
    elif name == "click":
        n = int(0.09 * SR)
        t = _t(n)
        x = (np.sin(2 * np.pi * 1700 * t) * 0.7 + _lowpass(np.random.default_rng(17).standard_normal(n), 5000) * 0.3) \
            * _decay(n, 0.0004, 0.008)
        k = int(0.045 * SR)
        x[k:] += x[:n - k] * 0.35
        y = _stereo(x)
    elif name == "stamp":
        n = int(0.4 * SR)
        thump = _sweep(n, 120, 52, 0.6) * _decay(n, 0.002, 0.07)
        slap = _lowpass(np.random.default_rng(18).standard_normal(n), 2200) * _decay(n, 0.0008, 0.018) * 0.7
        y = _stereo(thump + slap)
    elif name == "impact":
        n = int(0.9 * SR)
        sub = _sweep(n, 95, 36, 0.5) * _decay(n, 0.003, 0.22)
        crack = _lowpass(np.random.default_rng(19).standard_normal(n), 3500) * _decay(n, 0.0008, 0.03) * 0.5
        y = _stereo(sub + crack)
    elif name == "riser":
        n = int(0.9 * SR)
        p = np.linspace(0, 1, n)
        air = _band_noise(n, 300 + 4200 * p ** 2, 0.5, 20)
        tone = _sweep(n, 220, 1100, 2.0) * 0.35
        x = (air + tone) * p ** 2.4
        x[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
        y = _stereo(x, -0.2, 0.2)
    elif name == "shutter":
        n = int(0.12 * SR)
        rng = np.random.default_rng(21)
        x = np.zeros(n)
        for at, g in ((0.0015, 1.0), (0.062, 0.6)):
            i = int(at * SR)
            m = int(0.012 * SR)
            x[i:i + m] += _lowpass(rng.standard_normal(m), 4000) * _decay(m, 0.0003, 0.003) * g
        y = _stereo(x)
    else:
        raise ValueError(f"unknown sound '{name}'. Known: {', '.join(NAMES)}")
    y = y - y.mean(axis=0, keepdims=True)
    fi, fo = int(0.002 * SR), int(0.008 * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]
    y[-fo:] *= np.linspace(1, 0, fo)[:, None]
    y = y / (np.max(np.abs(y)) + 1e-9) * 10 ** (-3 / 20)
    return y.astype(np.float32)


def peak_offset(y):
    """Seconds from the file start to the centre of its loudest 10 ms window (both channels)."""
    np = _np()
    e = (y.astype(np.float64) ** 2).sum(axis=1)
    w = int(0.010 * SR)
    if len(e) <= w:
        return 0.0
    c = np.convolve(e, np.ones(w), "valid")
    return (int(np.argmax(c)) + w // 2) / SR


def _write_wav(path, y):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-c:a", "pcm_s24le", path], input=y.astype("float32").tobytes(), capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode()[-300:])


def read_wav(path):
    np = _np()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def max_momentary(path):
    """Loudest 400 ms momentary loudness (LUFS) of a file, via ffmpeg ebur128."""
    import re
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                        "ebur128=metadata=1,ametadata=mode=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    ms = [float(x) for x in re.findall(r"lavfi\.r128\.M=(-?[\d.]+)", r.stdout)]
    return max(ms) if ms else -99.0


def get(name):
    """(samples float32 (n,2), meta {name, length, peak, max_m}) from the cache, synthesizing on first use."""
    np = _np()
    os.makedirs(CACHE, exist_ok=True)
    wav, meta_p = os.path.join(CACHE, f"{name}.wav"), os.path.join(CACHE, f"{name}.json")
    if not (os.path.exists(wav) and os.path.exists(meta_p)):
        y = build(name)
        _write_wav(wav, y)
        pad = os.path.join(CACHE, f"_{name}_pad.wav")
        _write_wav(pad, np.vstack([np.zeros((SR // 2, 2), np.float32), y, np.zeros((SR // 2, 2), np.float32)]))
        meta = {"name": name, "length": round(len(y) / SR, 4), "peak": round(peak_offset(y), 4), "max_m": max_momentary(pad)}
        os.remove(pad)
        if meta["max_m"] < -80:
            os.remove(wav)
            raise RuntimeError(f"could not measure the loudness of sound '{name}' (ffmpeg ebur128); run doctor.py")
        with open(meta_p, "w") as f:
            json.dump(meta, f)
    with open(meta_p) as f:
        meta = json.load(f)
    return read_wav(wav), meta


def build_all():
    return {n: get(n)[1] for n in NAMES}


if __name__ == "__main__":
    print(json.dumps(build_all(), indent=1))
