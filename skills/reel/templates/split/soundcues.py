#!/usr/bin/env python3
"""soundcues.py: sound design from FILES on exact cut times (hook SFX), mixed under the voice. The voice is never
filtered: muffle windows low-pass only the SFX bus. Used by render.py when project.json has "sound": {"cues": [...]}.

project.json
  "sound": {
    "cues": [{"src": "sfx/impact.mp3", "at": 0.25,           cut time the FILE starts (s)
              "gain_db": -6 | "peak_db": -3,                  file gain, or the cue's sample peak in the mix (dBFS)
              "dur": 1.2, "fade_in": 0.05, "fade_out": 0.3,   trim + fades (s)
              "env": [[0, 1], [0.3, 1], [0.45, 0.2]],         gain breakpoints (s from the cue start, linear)
              "dry": true}],                                  true = not muffled (an inner-ear ring)
    "muffle": [{"t0": 2.40, "t1": 3.70, "hz": 600, "ramp": 0.06, "duck_db": -4}],
    "sfx_until": 5.6,                                         every cue is faded out by this cut time
    "ticks": {"only": ["slot "], "under_db": 22}             optional synth ticks on registered insert events
  }
Writes the mix to <out.wav>: 48 kHz stereo, voice master at -14 LUFS, integrated -14 LUFS, true peak <= -2 dBTP
(deliver.py then masters it). Prints a JSON report with the levels.

  PY soundcues.py <project> <out.wav>
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sound as S  # noqa: E402

SR = S.SR


def _db(x):
    return 20 * __import__("math").log10(max(x, 1e-9))


def _cue(np, project, c, n):
    x = S.read_audio(os.path.join(project, c["src"]))
    if c.get("dur"):
        x = x[:int(c["dur"] * SR)]
    m = len(x)
    t = np.arange(m) / SR
    g = np.ones(m)
    if c.get("env"):
        pts = sorted(c["env"])
        g *= np.interp(t, [p[0] for p in pts], [p[1] for p in pts])
    fi, fo = c.get("fade_in", 0.0), c.get("fade_out", 0.0)
    if fi > 0:
        g *= np.clip(t / fi, 0, 1)
    if fo > 0:
        g *= np.clip((t[-1] - t) / fo, 0, 1)
    x = x * g[:, None]
    if c.get("peak_db") is not None:
        x *= 10 ** (c["peak_db"] / 20) / (np.max(np.abs(x)) + 1e-9)
    else:
        x *= 10 ** (c.get("gain_db", 0.0) / 20)
    out = np.zeros((n, 2), np.float32)
    i0 = int(round(c["at"] * SR))
    j = min(n, i0 + m)
    if j > i0 >= 0:
        out[i0:j] = x[:j - i0]
    return out


def _lowpass(np, x, hz, work):
    src, dst = os.path.join(work, "_mf_in.wav"), os.path.join(work, "_mf_out.wav")
    S.write_wav(src, x)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", f"lowpass=f={hz}:p=2,lowpass=f={hz}:p=2",
                        "-c:a", "pcm_f32le", dst], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-300:])
    y = S.read_audio(dst)[:len(x)]
    for f in (src, dst):
        os.remove(f)
    return np.pad(y, ((0, len(x) - len(y)), (0, 0)))


def _muffle(np, bus, windows, work):
    n = len(bus)
    t = np.arange(n) / SR
    for w in windows:
        r = w.get("ramp", 0.06)
        mask = np.clip(np.minimum((t - w["t0"] + r) / r, (w["t1"] + r - t) / r), 0, 1)
        if not mask.any():
            continue
        wet = _lowpass(np, bus, w.get("hz", 600), work) * 10 ** (w.get("duck_db", 0.0) / 20)
        bus = bus * (1 - mask[:, None]) + wet * mask[:, None]
    return bus


def build(project, out_wav, spec=None):
    np = S._np()
    project = os.path.abspath(project)
    work = os.path.join(project, "work")
    pj = json.load(open(os.path.join(project, "project.json")))
    spec = spec or pj.get("sound") or {}
    voice, _ = S.master_voice(os.path.join(project, "assets", "aroll.mp4"), work)
    lb = json.load(open(os.path.join(project, "layout_boxes.json")))
    n = int(round(lb["frames"] / 30.0 * SR))
    voice = np.pad(voice, ((0, max(0, n - len(voice))), (0, 0)))[:n]
    wet = np.zeros((n, 2), np.float32)
    dry = np.zeros((n, 2), np.float32)
    for c in spec.get("cues", []):
        (dry if c.get("dry") else wet)[:] += _cue(np, project, c, n)
    wet = _muffle(np, wet, spec.get("muffle", []), work)
    bus = wet + dry
    if spec.get("sfx_until"):
        t = np.arange(n) / SR
        bus *= np.clip((spec["sfx_until"] - t) / 0.5, 0, 1)[:, None]
    ticks = np.zeros((n, 2), np.float32)
    tk, evs = spec.get("ticks"), []
    if tk:
        rng = np.random.default_rng(5)
        evs = S.pick_events(lb.get("events", []), {"sfx": {**tk, "kinds": {"tick": "tick"}, "min_gap": 0.6,
                                                          "max_per_10s": 4}}, n / SR)
        evs = [e for e in evs if e["kind"] == "tick"]
        for e in evs:
            s = S.sfx("tick", rng)
            i0 = int(round(e["t"] * SR))
            j = min(n, i0 + len(s))
            ticks[i0:j] += s[:j - i0]
        if ticks.any():   # loudest tick moment sits under_db below the voice (integrated), like sound.py's SFX
            tpath = os.path.join(work, "_ticks.wav")
            S.write_wav(tpath, ticks)
            _, _, t_m = S.loudness(tpath)
            S.write_wav(tpath, voice)
            v_i, _, _ = S.loudness(tpath)
            os.remove(tpath)
            ticks *= 10 ** ((v_i - tk.get("under_db", 22) - t_m) / 20)
    mbus, mrep = motion_bus(project, voice, n, pj, lb)
    mix = voice + bus + ticks + mbus
    mpath = os.path.join(work, "_cuemix.wav")
    S.write_wav(mpath, mix)
    m_i, _, _ = S.loudness(mpath)
    mix *= 10 ** ((S.VOICE_TARGET - m_i) / 20)
    S.write_wav(mpath, mix)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mpath, "-af",
                        "aresample=192000,alimiter=limit=0.7943:attack=1:release=40:level=0,aresample=48000",
                        "-c:a", "pcm_s24le", out_wav], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-400:])
    os.remove(mpath)
    f_i, f_tp, f_m = S.loudness(out_wav)
    g = 10 ** ((S.VOICE_TARGET - m_i) / 20)
    hook = int(round((spec.get("sfx_until") or 0) * SR))
    rep = {"mix": {"lufs": f_i, "tp": f_tp, "max_momentary": f_m},
           "sfx_peak_dbfs": round(_db(float(np.max(np.abs(bus))) * g), 1) if bus.any() else None,
           "voice_peak_dbfs_in_hook": round(_db(float(np.max(np.abs(voice[:hook]))) * g), 1) if hook else None,
           "ticks": len(evs) if tk else 0, "cues": len(spec.get("cues", [])),
           "motion_sfx": {k: mrep.get(k) for k in ("mode", "under_voice_db")} | {"placed": len(mrep.get("placed", []))}}
    return rep


def motion_bus(project, voice, n, pj, lb):
    """Motion v2 SFX (engine/motion/mixer.py) on the motion plan's events + the inserts' graphic events, at the
    project's density (motion.sfx: off | light | full). The voice always leads (>= 18 dB, light 20-22 dB)."""
    np = S._np()
    mot = pj.get("motion")
    plan_p = os.path.join(project, "work", "motion_plan.json")
    if mot is False or not os.path.exists(plan_p):
        return np.zeros((n, 2), np.float32), {"mode": "off", "placed": []}
    import motionlayer  # puts engine/motion on sys.path
    import mixer
    mode = motionlayer.M.config(pj)["sfx"]
    plan = json.load(open(plan_p))
    events = plan.get("events", []) + [{"t": e["t"], "kind": e["kind"], "what": e.get("what", "")}
                                       for e in lb.get("events", [])]
    tick_kinds = {"tick"} if (pj.get("sound") or {}).get("ticks") else set()   # never double the existing ticks
    events = [e for e in events if e.get("kind") not in tick_kinds]
    mute = [(w["t0"] - 0.1, w["t1"] + 0.1) for w in (pj.get("sound") or {}).get("muffle", [])]   # keep muffled moments clean
    events = [e for e in events if not any(a <= e["t"] <= b for a, b in mute)]
    v_lufs = mixer.voice_lufs(voice)
    bus, rep = mixer.build_bus(events, n, v_lufs, mode, include_inserts=True,
                               stem_path=os.path.join(project, "work", "motion_sfx_stem.wav"))
    mixer.write_report(project, rep)
    return bus, rep


def apply(project, rel_render):
    """Mix the cues under the voice and swap them into the render. The voice-only render is kept next to it as
    <stem>-voiceonly.mp4 (deliver.py masters both)."""
    project = os.path.abspath(project)
    src = os.path.join(project, rel_render)
    stem = os.path.splitext(src)[0]
    voiceonly = stem + "-voiceonly.mp4"
    wav = os.path.join(project, "work", "cue_mix.wav")
    rep = build(project, wav)          # build first: a failed mix never costs the render
    os.replace(src, voiceonly)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", voiceonly, "-i", wav, "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                        src], capture_output=True, text=True)
    if p.returncode:
        os.replace(voiceonly, src)
        raise RuntimeError("could not mux the sound cues: " + p.stderr[-300:])
    with open(os.path.join(project, "work", "sound_report.json"), "w") as f:
        json.dump(rep, f, indent=1)
    return rep, voiceonly


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) < 2:
        raise SystemExit(__doc__)
    print(json.dumps(build(a[0], a[1]), indent=1))
