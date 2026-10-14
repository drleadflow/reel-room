#!/usr/bin/env python3
"""sound.py: voice master + optional sound design for a render. Everything here is synthesized in numpy, so the
SFX and the bed are ours (no samples, no licences). Voice is never processed except one linear gain + a true-peak
guard; SFX sit >= 18 dB under the voice, the bed >= 20 dB under.

  python sound.py <project> <out.wav> [--sfx] [--bed] [--plan plan.json]
     events come from layout_boxes.json "events" (graphic entrances registered by the inserts), filtered/limited by
     the plan: {"sfx": {"kinds": {...}, "max_per_10s": 2.5, "min_gap": 1.2, "only": [...]}, "bed": {"style": "lofi"}}

Output: 48 kHz stereo 24-bit wav at -14 LUFS integrated, true peak <= -1.5 dBTP (checked after AAC by gallery.py).
"""
import json
import os
import re
import subprocess
import sys

SR = 48000
VOICE_TARGET = -14.0


def _np():
    try:
        import numpy as np  # noqa: F401
        return np
    except ImportError:
        venv = os.path.expanduser("~/.reel-room/venv/bin/python")
        os.execv(venv, [venv] + sys.argv)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def read_audio(path, sr=SR):
    np = _np()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def write_wav(path, x, sr=SR):
    np = _np()
    x = np.ascontiguousarray(x.astype(np.float32))
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
                        "-c:a", "pcm_s24le", path], input=x.tobytes(), capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode()[-400:])


def loudness(path, momentary=False):
    """(integrated LUFS, true peak dBTP, max momentary LUFS)"""
    r = run(["ffmpeg", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true",
             "-f", "null", "-"])
    err = r.stderr
    i = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", err)
    ms = [float(m) for m in re.findall(r"\bM:\s*(-?[\d.]+)", err) if m not in ("-inf",)]
    f = lambda v: float(v) if v not in (None, "-inf") else -99.0  # noqa: E731
    return f(i[-1] if i else None), f(tp[-1] if tp else None), (max(ms) if ms else -99.0)


# ------------------------------------------------------------------ synthesis
def _env(n, a, d, np):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / max(d, 1e-4))
    return e


def _lp(x, cutoff, np):
    """one-pole low-pass (cheap, smooth)"""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _bp_noise(n, f0, f1, rng, np):
    """noise swept through a band (FFT domain shaping per block) -> whoosh-like texture"""
    x = rng.standard_normal(n)
    out = np.zeros(n)
    blk = 1024
    for s in range(0, n, blk // 2):
        seg = x[s:s + blk]
        if len(seg) < 8:
            break
        w = np.hanning(len(seg))
        sp = np.fft.rfft(seg * w)
        fr = np.fft.rfftfreq(len(seg), 1 / SR)
        c = f0 + (f1 - f0) * (s / n)
        bw = c * 0.9
        sp *= np.exp(-((fr - c) / bw) ** 2)
        out[s:s + len(seg)] += np.fft.irfft(sp, len(seg))
    return out


def sfx(kind, rng):
    np = _np()
    if kind == "whoosh":
        n = int(0.42 * SR)
        x = _bp_noise(n, 500, 2600, rng, np)
        t = np.linspace(0, 1, n)
        x *= np.sin(np.pi * t) ** 1.6
    elif kind == "pop":
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 28) + 380
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.03, np)
    elif kind in ("tick", "click"):
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * 2400 * t) * 0.6 + rng.standard_normal(n) * 0.25) * _env(n, 0.0005, 0.006, np)
        x = _lp(x, 6000, np) if kind == "tick" else x
    elif kind == "thud":
        n = int(0.32 * SR)
        t = np.arange(n) / SR
        f = 120 * np.exp(-t * 12) + 48
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.003, 0.09, np)
        x += _lp(rng.standard_normal(n), 900, np) * _env(n, 0.001, 0.02, np) * 0.5
    elif kind == "scribble":
        n = int(0.55 * SR)
        t = np.arange(n) / SR
        x = _bp_noise(n, 2400, 3200, rng, np) * (0.55 + 0.45 * np.sin(2 * np.pi * 9 * t) ** 2)
        x *= np.minimum(1, t / 0.03) * np.minimum(1, (0.55 - t) / 0.08)
    elif kind == "flip":
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        x = _bp_noise(n, 1800, 900, rng, np) * _env(n, 0.01, 0.07, np)
        x += _bp_noise(n, 3000, 3000, rng, np) * _env(n, 0.001, 0.01, np) * 0.6
    else:
        raise ValueError(kind)
    x = x / (np.max(np.abs(x)) + 1e-9)
    return np.stack([x, x], 1).astype(np.float32)


def lofi_bed(seconds, seed=7):
    """Warm, quiet lo-fi loop: soft e-piano 7th chords, round sub, brushed hats, a little tape wobble and vinyl hiss."""
    np = _np()
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    out = np.zeros((n, 2))
    bpm = 78
    beat = 60 / bpm
    bar = 4 * beat
    # Fmaj9 - Em7 - Dm9 - Cmaj7 (voiced around middle C)
    chords = [[53, 57, 60, 64, 67], [52, 55, 59, 62, 67], [50, 53, 57, 60, 64], [48, 52, 55, 59, 62]]
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731
    t_all = np.arange(n) / SR
    wob = 1 + 0.0025 * np.sin(2 * np.pi * 0.35 * t_all)
    k = 0
    while k * bar < seconds + bar:
        ch = chords[k % 4]
        for hit, (off, vel) in enumerate([(0, 1.0), (2.5 * beat, 0.55)]):
            s0 = int((k * bar + off) * SR)
            ln = int(bar * 0.95 * SR) if hit == 0 else int(1.4 * beat * SR)
            if s0 >= n:
                break
            ln = min(ln, n - s0)
            t = np.arange(ln) / SR
            env = np.minimum(1, t / 0.012) * np.exp(-t / 1.6)
            tone = np.zeros(ln)
            for j, m in enumerate(ch):
                f = midi(m)
                ph = 2 * np.pi * f * np.cumsum(wob[s0:s0 + ln]) / SR
                tone += (np.sin(ph) + 0.18 * np.sin(2 * ph) * np.exp(-t / 0.25) + 0.06 * np.sin(3 * ph)) * (0.9 - 0.08 * j)
            tone *= env * vel / len(ch)
            pan = 0.12 * (1 if k % 2 else -1)
            out[s0:s0 + ln, 0] += tone * (1 - pan)
            out[s0:s0 + ln, 1] += tone * (1 + pan)
        # sub bass on the root
        s0 = int(k * bar * SR)
        if s0 < n:
            ln = min(int(bar * SR), n - s0)
            t = np.arange(ln) / SR
            f = midi(ch[0] - 12)
            b = np.sin(2 * np.pi * f * t) * np.minimum(1, t / 0.02) * np.exp(-t / 2.2) * 0.35
            out[s0:s0 + ln] += b[:, None]
        # soft kick on 1 and 3, brushed hat on the off-beats (swung)
        for q in range(4):
            s0 = int((k * bar + q * beat) * SR)
            if s0 >= n:
                continue
            if q in (0, 2):
                ln = min(int(0.25 * SR), n - s0)
                t = np.arange(ln) / SR
                kk = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t * 30) + 45) / SR) * np.exp(-t / 0.07) * 0.5
                out[s0:s0 + ln] += kk[:, None]
            s1 = int((k * bar + q * beat + beat * 0.58) * SR)
            if s1 < n:
                ln = min(int(0.06 * SR), n - s1)
                h = rng.standard_normal(ln) * np.exp(-np.arange(ln) / SR / 0.012) * 0.08
                h = h - _lp(h, 5000, np)
                out[s1:s1 + ln, 0] += h * 0.9
                out[s1:s1 + ln, 1] += h * 1.1
        k += 1
    hiss = _lp(rng.standard_normal(n), 7000, np) * 0.004
    out += hiss[:, None]
    # warm it: gentle low-pass on the whole bed
    out[:, 0] = _lp(out[:, 0], 3800, np)
    out[:, 1] = _lp(out[:, 1], 3800, np)
    fade = int(1.2 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return (out / (np.max(np.abs(out)) + 1e-9)).astype(np.float32)


# ------------------------------------------------------------------ planning + mix
SYNTH_KINDS = {"whoosh", "pop", "tick", "click", "thud", "scribble", "flip"}


def pick_events(events, plan, total):
    cfg = plan.get("sfx", {})
    kinds = cfg.get("kinds", {})          # map registered kind -> sfx kind (or null to drop)
    only = cfg.get("only")                # list of substrings of `what` to keep
    min_gap = cfg.get("min_gap", 1.2)
    cap = cfg.get("max_per_10s", 2.5)
    out = []
    for e in sorted(events, key=lambda e: e["t"]):
        k = kinds.get(e["kind"], e["kind"])
        k = {"type": "tick", "stamp": "thud"}.get(k, k)          # motion v2 kinds -> the synth kit
        if not k or k not in SYNTH_KINDS:
            continue
        if only and not any(o in e.get("what", "") for o in only):
            continue
        if out and e["t"] - out[-1]["t"] < min_gap:
            continue
        win = [x for x in out if e["t"] - x["t"] < 10]
        if len(win) + 1 > cap * 1.0 + 1e-9 and len(win) >= int(cap):
            continue
        out.append({"t": e["t"], "kind": k, "what": e.get("what", "")})
    return [e for e in out if e["t"] < total - 0.2]


def master_voice(src, work):
    """Two-pass loudnorm of the voice alone (once, cached) -> float array at SR."""
    np = _np()
    cache = os.path.join(work, "voice_master.wav")
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(src):
        r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn", "-af",
                 "loudnorm=I=-14:TP=-2:LRA=9:print_format=json", "-f", "null", "-"])
        d = json.loads(re.search(r"\{[^{}]+\}", r.stderr[r.stderr.rfind("[Parsed_loudnorm"):], re.S).group(0))
        af = (f"loudnorm=I=-14:TP=-2:LRA=9:measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}"
              f":measured_thresh={d['input_thresh']}:offset={d['target_offset']},aresample={SR}")
        p = run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-af", af, "-ac", "2", "-c:a", "pcm_s24le", "-ar", str(SR), cache])
        if p.returncode:
            raise RuntimeError(p.stderr[-400:])
    v = read_audio(cache)
    return v, cache


def build(project, out_wav, use_sfx=False, use_bed=False, plan=None, motion=True):
    np = _np()
    project = os.path.abspath(project)
    work = os.path.join(project, "work")
    os.makedirs(work, exist_ok=True)
    plan = plan or {}
    voice, _ = master_voice(os.path.join(project, "assets", "aroll.mp4"), work)
    lb = json.load(open(os.path.join(project, "layout_boxes.json")))
    total = lb["frames"] / 30.0
    n = int(round(total * SR))
    voice = np.pad(voice, ((0, max(0, n - len(voice))), (0, 0)))[:n]
    mix_parts = {"voice": voice}
    report = {"sfx": [], "bed": None}
    rng = np.random.default_rng(3)
    vpath = os.path.join(work, "_voice.wav")
    write_wav(vpath, voice)
    v_i, v_tp, _ = loudness(vpath)
    report["voice"] = {"lufs": v_i, "tp": v_tp}
    if use_sfx:
        evs = pick_events(lb.get("events", []), plan, total)
        track = np.zeros((n, 2), np.float32)
        gains = plan.get("sfx", {}).get("gain", {})
        for e in evs:
            s = sfx(e["kind"], rng) * float(gains.get(e["kind"], 1.0))
            i0 = int(round((e["t"] + plan.get("sfx", {}).get("lead", {}).get(e["kind"], 0.0)) * SR))
            i0 = max(0, i0)
            j = min(n, i0 + len(s))
            track[i0:j] += s[:j - i0]
        spath = os.path.join(work, "_sfx.wav")
        write_wav(spath, track)
        _, _, mmax = loudness(spath, momentary=True)
        want = v_i - plan.get("sfx", {}).get("under_db", 20.0)   # loudest SFX moment vs voice integrated
        g = 10 ** ((want - mmax) / 20) if mmax > -90 else 0
        track *= g
        write_wav(spath, track)
        _, s_tp, s_m = loudness(spath, momentary=True)
        mix_parts["sfx"] = track
        report["sfx"] = evs
        report["sfx_level"] = {"max_momentary": s_m, "under_voice_db": round(v_i - s_m, 1)}
    if use_bed:
        bed = lofi_bed(total + 0.1)[:n]
        bed = np.pad(bed, ((0, max(0, n - len(bed))), (0, 0)))
        # duck under speech: voice envelope (50 ms) -> up to 5 dB down
        env = np.sqrt(np.convolve((voice[:, 0] ** 2), np.ones(2400) / 2400, mode="same"))
        env = env / (np.percentile(env, 95) + 1e-9)
        duck = 10 ** (-5 * np.clip(env, 0, 1) / 20)
        duck = np.convolve(duck, np.ones(4800) / 4800, mode="same")
        bed *= duck[:, None]
        bpath = os.path.join(work, "_bed.wav")
        write_wav(bpath, bed)
        b_i, _, _ = loudness(bpath)
        want = v_i - plan.get("bed", {}).get("under_db", 22.0)
        bed *= 10 ** ((want - b_i) / 20)
        write_wav(bpath, bed)
        b_i2, _, _ = loudness(bpath)
        mix_parts["bed"] = bed
        report["bed"] = {"lufs": b_i2, "under_voice_db": round(v_i - b_i2, 1)}
    if motion:   # motion v2 SFX on transitions (+ new graphics when the style has no SFX of its own)
        import soundcues
        pj = json.load(open(os.path.join(project, "project.json")))
        lb_ev = lb if not use_sfx else {**lb, "events": []}
        mbus, mrep = soundcues.motion_bus(project, voice, n, pj, lb_ev)
        if mrep.get("placed"):
            mix_parts["motion_sfx"] = mbus
        report["motion_sfx"] = {"mode": mrep.get("mode"), "placed": len(mrep.get("placed", [])),
                                "under_voice_db": mrep.get("under_voice_db")}
    mix = sum(mix_parts.values())
    mpath = os.path.join(work, "_mix.wav")
    write_wav(mpath, mix)
    m_i, _, _ = loudness(mpath)
    mix *= 10 ** ((VOICE_TARGET - m_i) / 20)
    write_wav(mpath, mix)
    # true-peak guard: oversampled limiter at -2.0 dBTP (AAC adds ~0.3 dB)
    p = run(["ffmpeg", "-v", "error", "-y", "-i", mpath, "-af",
             "aresample=192000,alimiter=limit=0.7943:attack=2:release=60:level=0,aresample=48000",
             "-c:a", "pcm_s24le", out_wav])
    if p.returncode:
        raise RuntimeError(p.stderr[-400:])
    f_i, f_tp, _ = loudness(out_wav)
    report["mix"] = {"lufs": f_i, "tp": f_tp}
    for f in ("_voice.wav", "_mix.wav"):
        try:
            os.remove(os.path.join(work, f))
        except OSError:
            pass
    return report


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    plan = json.load(open(sys.argv[sys.argv.index("--plan") + 1])) if "--plan" in sys.argv else {}
    print(json.dumps(build(a[0], a[1], "--sfx" in sys.argv, "--bed" in sys.argv, plan), indent=1))
