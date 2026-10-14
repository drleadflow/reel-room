"""mixer.py: sound effects placed ON visual events, voice always leads.

  bus, report = mixer.build_bus(events, n_samples, voice_lufs, mode="light", include_inserts=True)

events: the motion plan's event log (transitions, camera moves) plus the composition's graphic events
        ({t, kind, what}); kinds are mapped to the kit in sfxkit.py.
mode:   off   no SFX
        light (default) sparse: transitions and the first entrance of a new graphic, at least 1.5 s apart,
              at most 3 per 10 s, every sound 22 dB under the voice (transitions 20 dB)
        full  every mapped event, at least 0.18 s apart, at most 14 per 10 s, 20 dB under (transitions 18 dB)
The loudest 400 ms of the SFX bus never comes closer than 18 dB to the voice's integrated loudness (hard floor).
Each sound starts at `event_time - peak` so its loudest 10 ms lands on the event's frame.
Camera settles, punches and reframes are silent by design (they are picture, not sound).
"""
import json
import os
import subprocess
import tempfile

import sfxkit

SR = sfxkit.SR
FLOOR_DB = 18.0
MODES = {
    "light": {"min_gap": 1.5, "per10s": 3, "under": 22.0, "under_transition": 20.0},
    "full": {"min_gap": 0.18, "per10s": 14, "under": 20.0, "under_transition": 18.0},
}
# composition event kind -> kit sound (None = silent)
INSERT_SOUND = {"whoosh": "whoosh_soft", "pop": "pop", "click": "click", "tick": "tick", "thud": "stamp",
                "flip": "swish", "scribble": None, "enter": "pop", "type": "tick", "stamp": "stamp", "impact": "impact"}


def _np():
    import numpy as np
    return np


def pick(events, mode, total, include_inserts=True):
    """Density filter -> [{t, sound, kind, what, transition}] sorted by time."""
    if mode not in MODES:
        return []
    m = MODES[mode]
    cands = []
    for e in events:
        k = e.get("kind")
        if k == "transition":
            snd, pri = e.get("sound"), 0
        elif e.get("src") == "motion":
            snd, pri = None, 9         # camera moves are silent
        elif include_inserts:
            snd, pri = INSERT_SOUND.get(k, None), 1
        else:
            snd, pri = None, 9
        if mode == "full" and k == "type" and include_inserts:
            snd = "tick"
        if not snd or e["t"] > total - 0.15:
            continue
        cands.append({"t": float(e["t"]), "sound": snd, "kind": k, "what": e.get("what", ""), "pri": pri,
                      "transition": k == "transition"})
    chosen = []
    for c in sorted(cands, key=lambda c: (c["pri"], c["t"])):
        if any(abs(c["t"] - x["t"]) < m["min_gap"] for x in chosen):
            continue
        if sum(1 for x in chosen if abs(c["t"] - x["t"]) < 5.0) >= m["per10s"]:
            continue
        chosen.append(c)
    return sorted(chosen, key=lambda c: c["t"])


def _write(path, y):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-c:a", "pcm_s24le", path], input=y.astype("float32").tobytes(), capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode()[-300:])


def integrated(path):
    import re
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -70.0


def voice_lufs(voice):
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        _write(tmp, voice)
        return integrated(tmp)
    finally:
        os.unlink(tmp)


def build_bus(events, n, v_lufs, mode="light", include_inserts=True, stem_path=None):
    """-> (bus float32 (n,2), report). report['placed'] = [{t, sound, start, gain_db, under_db}]."""
    np = _np()
    bus = np.zeros((n, 2), np.float32)
    rep = {"mode": mode, "voice_lufs": round(v_lufs, 2), "placed": []}
    if mode == "off" or mode not in MODES:
        return bus, rep
    m = MODES[mode]
    total = n / SR
    for c in pick(events, mode, total, include_inserts):
        y, meta = sfxkit.get(c["sound"])
        under = max(FLOOR_DB, m["under_transition"] if c["transition"] else m["under"])
        gain_db = (v_lufs - under) - meta["max_m"]
        start = c["t"] - meta["peak"]
        i0 = int(round(start * SR))
        seg = y * (10 ** (gain_db / 20))
        if i0 < 0:
            seg, i0 = seg[-i0:], 0
        j = min(n, i0 + len(seg))
        if j <= i0:
            continue
        bus[i0:j] += seg[:j - i0]
        rep["placed"].append({"t": round(c["t"], 3), "sound": c["sound"], "kind": c["kind"], "what": c["what"],
                              "start": round(start, 4), "peak": meta["peak"], "gain_db": round(gain_db, 2),
                              "under_db": under})
    if rep["placed"]:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            _write(tmp, bus)
            mx = sfxkit.max_momentary(tmp)
            if v_lufs - mx < FLOOR_DB:   # stacked sounds: pull the whole bus down to the floor
                bus *= 10 ** (-(FLOOR_DB - (v_lufs - mx) + 0.3) / 20)
                _write(tmp, bus)
                mx = sfxkit.max_momentary(tmp)
            rep["bus_max_momentary"] = round(mx, 2)
            rep["under_voice_db"] = round(v_lufs - mx, 2)
        finally:
            os.unlink(tmp)
    if stem_path:
        _write(stem_path, bus)
        rep["stem"] = stem_path
    return bus, rep


def write_report(project, rep):
    os.makedirs(os.path.join(project, "work"), exist_ok=True)
    with open(os.path.join(project, "work", "motion_sfx.json"), "w") as f:
        json.dump(rep, f, indent=1)
