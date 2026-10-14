"""Snap EDL cut points to real silence and audit every join.

Why: Whisper word STARTS alone make bad cut anchors. Starts say nothing about where a word ends, small.en
drifts 0.2-0.4 s around pauses, it drops disfluencies ("so I... so I"), and a text re-check of the finished cut
cannot catch a clipped word because Whisper hears "equipm-" as "equipment". So we measure audio, not text:
  timing truth  = medium.en word START and END on the source, only around the cut points (work/words_<clip>_precise.json)
  cut position  = inside a measured silence run (RMS envelope), never inside a speech run
  audit         = energy at each join + fragments before an in-point + repeated words across a join
  joins         = every join of the ASSEMBLED cut transcribed alone (2.6 s window) and compared with the words
                  that should sit on each side of it
Thresholds are measured per clip from the noise floor (10th percentile of the energy envelope), never fixed.

Usage (python = the Reel Room venv python):
  splice.py <project> words [--full|--windows]  # medium.en: whole clip when it is <= 6 min, else +-1.5 s windows around every EDL in/out (merged, cached)
  splice.py <project> snap            # rewrites edl.json in/out from the line text, prints a report, keeps edl.bak.json
  splice.py <project> audit           # audits the current edl.json against the source audio (run before assemble)
  splice.py <project> joins [--strict]  # audits assets/aroll.mp4 + solo transcription of each join -> work/joins.json
                                        # verdict per join = energy + text (see cmd_joins); waive with project.json joins_ok
  splice.py <project> env <clip> <t0> <t1> [--step 0.02]  # energy envelope (time:dB) + word boundaries, to decide takes / false starts
Add --json for machine-readable output. edl.json entries may carry lock_in / lock_out to keep an edge as written.
Optional names.txt (in the project or its parent, one name per line) is fed to Whisper as a spelling hint.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

HOP = 0.01          # envelope step, s
HOLD = 0.15         # a cut point needs this much continuous quiet (plosive closures are ~60-100 ms, breaths last longer)
PAD_OUT, PAD_IN = 0.06, 0.05
MAX_TAIL = 0.45     # never extend an out more than this past the last word's end
BREATH_DB = 10      # quiet = under noise floor + this; breath sits a little above the floor
SPEECH_ABOVE_FLOOR = 24   # voice = noise floor + 24 dB (clamped), measured per clip
SPEECH_CLAMP = (-52.0, -38.0)
VOICED_ABOVE_FLOOR = 18   # a frame is "voiced" above floor + 18 dB (soft consonants included, room noise and most breaths excluded)
PHANTOM_ABOVE_FLOOR = 14  # a word whose loudest frame stays under floor + 14 dB was never spoken
RUN_GAP = 0.08            # voiced frames closer than this belong to one run (plosive closures, short dips)
RUN_MIN = 0.03
MIN_WORD = 0.045          # a word left with less voiced time than this after trimming is a phantom
DEAD_AIR = 0.12           # an in-point may sit at most this far before the first voiced frame of its first word
WIN = 1.5           # precise-word window half-width around each cut point
JOIN_WIN = 2.6      # solo transcription window per join
PRECISE_MODEL = "medium.en"
FULL_PASS_MAX = 360.0   # clips up to 6 min get a whole-clip medium.en pass (better word starts after pauses)
WORKERS = 3          # parallel Whisper calls (each short window costs a full 30 s encoder pass, so threads help)

norm = C.norm


class Env:
    """energy envelope of one clip + the thresholds measured from it"""

    def __init__(self, db, floor):
        self.db, self.floor = db, floor
        self.speech = float(min(max(floor + SPEECH_ABOVE_FLOOR, SPEECH_CLAMP[0]), SPEECH_CLAMP[1]))
        self.q = db < floor + BREATH_DB
        self.voiced = float(floor + VOICED_ABOVE_FLOOR)
        self._runs = None

    def runs(self):
        """voice runs [[start,end],...] in seconds: frames above the clip's voice level, gaps under RUN_GAP merged, blips dropped"""
        if self._runs is None:
            v = self.db > self.speech
            runs, i, n = [], 0, len(v)
            while i < n:
                if v[i]:
                    j = i
                    while j < n and v[j]:
                        j += 1
                    runs.append([i * HOP, j * HOP]); i = j
                else:
                    i += 1
            merged = []
            for r in runs:
                if merged and r[0] - merged[-1][1] < RUN_GAP:
                    merged[-1][1] = r[1]
                else:
                    merged.append(r)
            self._runs = [[round(a, 3), round(b, 3)] for a, b in merged if b - a >= RUN_MIN]
        return self._runs


def read_wav(path):
    import numpy as np
    w = wave.open(str(path))
    sr, ch = w.getframerate(), w.getnchannels()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def load_env(path) -> Env:
    import numpy as np
    a, sr = read_wav(path)
    hop = int(sr * HOP)
    n = len(a) // hop
    rms = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) / 32768
    db = 20 * np.log10(rms + 1e-9)
    db = np.convolve(db, np.ones(3) / 3, mode='same')
    return Env(db, float(np.percentile(db, 10)))


def refine_words(words, env, ks='s', ke='e', kt='w', protect=None):
    """Whisper stretches a word across the silence next to it and sometimes invents one (it hears a breath or a join as "If").
    Trim every word to the voiced energy (frames above the clip's voice level) it really overlaps, and drop phantoms:
      - a word whose frames never rise above the quiet level (floor + 10 dB) and touch no voice at all
      (a phantom that sits on voiced frames, like a breath next to a join, is caught by drop_join_phantoms instead)
    Returns (words, dropped) with dropped = [(text, time)]. Edges that already sit inside a voiced run are left alone, so
    touching words never stack, and very short words (stacked timestamps) are never dropped for being short.
    protect(word) -> True keeps a word no matter what (used when it matches the line the speaker was cutting to)."""
    runs = env.runs()
    out, dropped = [], []
    pad_s, pad_e = 0.04, 0.05
    for w in words:
        a, b = float(w[ks]), float(w[ke])
        ov = [r for r in runs if min(r[1], b) - max(r[0], a) > 0]
        vo = sum(min(r[1], b) - max(r[0], a) for r in ov)
        if not ov:
            i0, i1 = int(a / HOP), max(int(a / HOP) + 1, int(b / HOP))
            peak = float(env.db[i0:i1].max()) if i0 < len(env.db) else 0.0
            if peak < env.floor + BREATH_DB and not (protect and protect(w)):
                dropped.append((w[kt], round(a, 2)))
            else:
                out.append(dict(w))
            continue
        na, nb = a, b
        if ov[0][0] > a:
            na = max(a, ov[0][0] - pad_s)
        if ov[-1][1] < b:
            nb = min(b, ov[-1][1] + pad_e)
        out.append({**w, ks: round(na, 3), ke: round(max(nb, na + 0.02), 3)})
    return out, dropped


def line_tokens(segs, t, ks_frame=True):
    """normalised tokens of the line of the segment that contains cut time t"""
    for sg in segs:
        if sg['frame'] / 30 <= t < (sg['frame'] + sg['frames']) / 30:
            return [norm(x) for x in sg.get('line', '').split() if norm(x)]
    return []


def matches_line(text, toks, k=None, fuzzy=0.8):
    """does this caption word match one of the (first/last k, or all) tokens of a line?"""
    w = norm(text)
    pool = toks if k is None else toks[:k] + toks[-k:]
    return bool(w) and any(w == h or difflib.SequenceMatcher(None, w, h).ratio() >= fuzzy for h in pool)


def drop_join_phantoms(words, segs, env, ks='start', ke='end', kt='text', possible=None):
    """Whisper hears a breath or the seam of a join as a word ("If insulin is..." when only "insulin is..." was said). On the
    finished cut (words/segs on the cut timeline, each word belongs to the segment whose frame range holds its midpoint), a
    word in the first or last two positions of a segment is dropped only when ALL of these hold:
      - it does not match (same norm(), fuzzy 0.8) any of the first/last 3 tokens of that segment's `line`,
      - it is preceded by silence (the 60 ms before it dip below noise floor + 10 dB), and
      - it never reaches the clip's voice level before the neighbouring word's onset (the last 60 ms are excluded).
    A word that matches nothing but fails the energy test is KEPT and appended to `possible` as (text, time): captions must
    never lose a spoken word. Returns (words, dropped[(text, time)])."""
    drop = set()
    for sg in segs:
        toks = [norm(x) for x in sg.get('line', '').split() if norm(x)]
        if not toks:
            continue
        f0, f1 = sg['frame'] / 30, (sg['frame'] + sg['frames']) / 30
        idx = [i for i, w in enumerate(words) if f0 <= (w[ks] + w[ke]) / 2 < f1]
        for order in (idx, idx[::-1]):
            for i in order[:2]:
                w = words[i]
                if matches_line(w[kt], toks, 3):
                    break
                a, b = w[ks], w[ke]
                i0 = min(len(env.db) - 1, int(a / HOP)); i1 = max(i0 + 1, int((b - min(0.06, 0.6 * (b - a))) / HOP))
                lead = env.db[max(0, int((a - 0.06) / HOP)):i0 + 2].min()      # silence right before (or at the start of) the word
                if env.db[i0:i1].max() < env.speech and lead < env.floor + BREATH_DB:
                    drop.add(i)
                else:
                    if possible is not None:
                        possible.append((w[kt], round(a, 2)))
                    break
    return [w for i, w in enumerate(words) if i not in drop], [(words[i][kt], round(words[i][ks], 2)) for i in sorted(drop)]


def run_at(q, i, k):
    return i >= 0 and i + k <= len(q) and q[i:i + k].all()


def dip(db, a, b):
    """quietest 10 ms frame between a and b (where two words touch, cut at the valley)"""
    import numpy as np
    i, j = int(a / HOP), max(int(a / HOP) + 1, int(b / HOP))
    return round((i + int(np.argmin(db[i:j]))) * HOP, 3)


def snap_out(env, end, hi=None):
    """cut where the voice stops: first silence run after the last word, but before any breath that follows it.
    hi = never look past this time (used when words were removed right after this one)"""
    q, db = env.q, env.db
    k = int(HOLD / HOP); i = int(end / HOP)
    lim = int((end + MAX_TAIL) / HOP)
    if hi is not None:
        lim = max(i + 1, min(lim, int(hi / HOP)))
    while i < lim:
        if run_at(q, i, k):
            return round(i * HOP + PAD_OUT, 3), 'ok'
        if i < len(db) and db[i] < env.speech and run_at(db < env.speech, i, k):   # breath / noise after the word, not silence
            return round(i * HOP + 0.04, 3), 'ok (cut before a breath)'
        i += 1
    return dip(db, end - 0.03, end + 0.25 if hi is None else max(end, hi)), 'TOUCHING (next word starts right away: cut at the energy valley, listen)'


def snap_in(env, start, lo=None):
    """start just before the voice: after the last silence, but skipping a breath that sits right before the word.
    lo = never look back before this time (used when words were removed right before this one)"""
    q, db = env.q, env.db
    k = int(HOLD / HOP); i = int(start / HOP)
    lim = int((start - 0.6) / HOP)
    if lo is not None:
        lim = min(i - 1, max(lim, int(lo / HOP)))
    while i > lim:
        if run_at(q, i - k, k):
            t = round(i * HOP - PAD_IN, 3)
            if start - t > 0.18 and (db[int(t / HOP):int((start - 0.04) / HOP)] < env.speech).all():
                return round(start - 0.06, 3), 'ok (skipped a breath)'
            return t, 'ok'
        i -= 1
    return dip(db, start - 0.25 if lo is None else min(start, lo), start + 0.02), 'TOUCHING (previous word runs into this one: cut at the energy valley, listen)'


def anchor(words, line, t_in, t_out, lock_in=False, lock_out=False):
    """first/last word of the line, matched near the EDL's current in/out.
    A locked edge is trusted: its word is simply the word nearest that edge (no text match needed)."""
    toks = [norm(x) for x in line.split() if norm(x)]
    first, last = toks[0], toks[-1]
    near = [w for w in words if t_in - 1.0 <= w['s'] <= t_out + 1.0] or words
    fs = near if lock_in else ([w for w in near if norm(w['w']) == first] or near)
    ls = near if lock_out else ([w for w in near if norm(w['w']) == last] or near)
    if lock_in:
        fs = [w for w in near if w['e'] > t_in + 0.02] or near
        fw = min(fs, key=lambda w: abs(w['s'] - t_in))
    else:
        fw = min(fs, key=lambda w: abs(w['s'] - t_in))
    if lock_out:
        ls = [w for w in near if w['s'] < t_out - 0.02] or near
        lw = min(ls, key=lambda w: abs(w['e'] - t_out))
    else:
        lw = min(ls, key=lambda w: abs(w['e'] - t_out))
    return fw, lw


def words_between(words, a, b):
    return [w for w in words if w['e'] > a and w['s'] < b]


# --------------------------------------------------------------------------------------------- words (precise)
def windows_for(edl, clip, dur, full=False):
    """+-WIN around every in/out of this clip, widened to a 0.5 s grid (stable cache keys), merged"""
    if full:
        return [[0.0, round(dur, 1)]]
    import math
    raw = []
    for s in edl:
        if s['clip'] != clip:
            continue
        for t in (s['in'], s['out']):
            raw.append([max(0.0, math.floor((t - WIN) * 2) / 2), min(dur, math.ceil((t + WIN) * 2) / 2)])
    raw.sort()
    out = []
    for a, b in raw:
        if out and a <= out[-1][1] + 0.5:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def clip_key(proj, clip):
    info = C.source_info(proj).get(clip, {})
    return info.get('hash') or C.content_hash(Path(proj) / 'work' / f'{clip}.wav')


names_prompt = C.names_prompt


def transcribe_window(model, audio, a, b, prompt, words=True):
    """deterministic (greedy-free beam 5, temperature 0) transcription of audio[a:b] seconds; times are source times"""
    segs, _ = model.transcribe(audio[int(a * 16000):int(b * 16000)], language='en', word_timestamps=words,
                               condition_on_previous_text=False, initial_prompt=prompt, beam_size=5, temperature=0.0)
    segs = list(segs)
    if not words:
        return ' '.join(s.text.strip() for s in segs).strip()
    return C.drop_zero_length([{'w': w.word.strip(), 's': round(w.start + a, 3), 'e': round(w.end + a, 3), 'p': round(w.probability, 3)}
                               for s in segs for w in s.words])


def cmd_words(proj, edl, out, mode='auto'):
    """mode: 'auto' = whole clip when it is <= 6 min, windows around the cut points for longer clips; or 'full' / 'windows'"""
    import numpy as np
    prompt = names_prompt(proj)
    pk = hashlib.blake2b((prompt or '').encode(), digest_size=4).hexdigest()
    model, res = None, {}
    if prompt is None:
        out.log('note: no names hint. ' + C.NAMES_HINT)
    for clip in sorted({s['clip'] for s in edl}):
        wav = Path(proj) / 'work' / f'{clip}.wav'
        if not wav.exists():
            C.fail(f'{wav} is missing.', 'Run ingest.py first (it extracts work/<clip>.wav).', out.json)
        a16, sr = read_wav(wav)
        audio = (a16 / 32768.0).astype(np.float32)
        dur = len(audio) / sr
        full = mode == 'full' or (mode == 'auto' and dur <= FULL_PASS_MAX)
        wins = windows_for(edl, clip, dur, full)
        key = clip_key(proj, clip)
        cdir = C.CACHE / key / 'precise'
        cdir.mkdir(parents=True, exist_ok=True)
        allw, hit, t0 = [], 0, time.time()
        todo = []
        for a, b in wins:
            cf = cdir / f'{PRECISE_MODEL}_{a}_{b}_{pk}.json'
            if cf.exists():
                allw += C.read_json(cf); hit += 1
            else:
                todo.append((a, b, cf))
        if todo:
            nw = 1 if full else WORKERS
            model = C.whisper_model(PRECISE_MODEL, nw)
            if full:
                out.log(f'{clip}: medium.en over the whole clip ({dur:.0f} s) ...')

            def one(job):
                a, b, cf = job
                ws = transcribe_window(model, audio, a, b, prompt)
                C.write_json(cf, ws, indent=None)
                return ws
            with ThreadPoolExecutor(nw) as ex:
                for ws in ex.map(one, todo):
                    allw += ws
        allw.sort(key=lambda w: (w['s'], w['e']))
        allw, dropped = refine_words(allw, load_env(wav))
        for t, at in dropped:
            out.log(f'  dropped phantom: {t} @{at}')
        C.write_json(Path(proj) / 'work' / f'words_{clip}_precise.json', allw, indent=None)
        C.write_json(Path(proj) / 'work' / f'words_{clip}_precise.windows.json', wins, indent=None)
        covered = sum(b - a for a, b in wins)
        out.log(f'{clip}: {len(allw)} words from {"the whole clip" if full else str(len(wins)) + " windows"} '
                f'({covered:.0f} s of {dur:.0f} s), {hit} cached, {time.time() - t0:.1f}s')
        res[clip] = {'words': len(allw), 'dropped_phantoms': dropped, 'mode': 'full' if full else 'windows', 'windows': wins, 'cached_windows': hit,
                     'seconds': round(time.time() - t0, 1)}
    out.result({'ok': True, 'command': 'words', 'clips': res})


# --------------------------------------------------------------------------------------------- env
def cmd_env(proj, clip, t0, t1, step, out):
    wav = Path(proj) / 'work' / f'{clip}.wav'
    if not wav.exists():
        C.fail(f'{wav} is missing (unknown clip {clip}?).', 'Run ingest.py first, and use a clip id from sources.json (c1, c2...).', out.json)
    import numpy as np
    env = load_env(wav)
    k = max(1, round(step / HOP))
    quiet = env.floor + BREATH_DB
    out.log(f'clip {clip}  {t0:.2f}-{t1:.2f} s  step {k * HOP:.2f}  noise floor {env.floor:.0f} dB, quiet < {quiet:.0f} dB, voice > {env.speech:.0f} dB')
    rows, line = [], []
    i0, i1 = max(0, int(t0 / HOP)), min(len(env.db), int(t1 / HOP))
    for i in range(i0, i1, k):
        d = float(env.db[i:i + k].max())
        mark = '_' if d < quiet else ('#' if d > env.speech else '-')
        rows.append({'t': round(i * HOP, 2), 'db': round(d, 1), 'state': {'_': 'quiet', '-': 'sound', '#': 'voice'}[mark]})
        line.append(f'{i * HOP:.2f}:{d:.0f}{mark}')
        if len(line) == 8:
            out.log('  '.join(line)); line = []
    if line:
        out.log('  '.join(line))
    ws, kind = C.load_words(proj, clip)
    inr = [w for w in ws if w['e'] > t0 and w['s'] < t1]
    out.log(f'\nwords ({kind or "none"}): ' + ('  '.join(f"{w['s']:.2f}-{w['e']:.2f} {w['w']}" for w in inr) or '(none in range)'))
    out.log('legend: _ quiet (cut here)   - breath/room/mouth noise   # voice')
    out.result({'ok': True, 'command': 'env', 'clip': clip, 'floor_db': round(env.floor, 1), 'quiet_db': round(quiet, 1),
                'speech_db': round(env.speech, 1), 'envelope': rows, 'words': inr})


# --------------------------------------------------------------------------------------------- snap / audit
MAX_MOVE = 0.6     # snap never moves an edge more than this from its EDL value; bigger moves are only reported (WOULD MOVE)
MIN_GAP = 0.04      # adjacent segments of the same clip need at least this much source time between out(A) and in(B)


def onset_after(env, t, limit=1.0):
    """time of the first voiced frame at or after t (None if there is none within `limit` seconds)"""
    i, lim = int(t / HOP), min(len(env.db), int((t + limit) / HOP))
    while i < lim:
        if env.db[i] > env.voiced:
            return round(i * HOP, 3)
        i += 1
    return None


def settle_out(env, o, lw_end):
    """an out-point must not sit on a rising energy onset: the 40 ms after it must be below voice level, else back off to the valley"""
    db = env.db
    clear = lambda i: i + 4 > len(db) or bool((db[i:i + 4] < env.speech).all())  # noqa: E731
    i = int(o / HOP)
    if clear(i):
        return o, None
    lo = int(max(lw_end, o - 0.3) / HOP)
    j = i
    while j > lo and not clear(j):
        j -= 1
    if clear(j):
        return round(j * HOP, 3), 'ok (moved back from a rising onset)'
    return dip(db, lw_end - 0.03, o), 'TOUCHING (an onset follows the last word: cut at the energy valley, listen)'


def load_segments_ok(proj):
    """project.json "segments_ok": [{"id":"n1d","why":"listened, fine"}] silences audit notes for those segments"""
    pj = Path(proj) / 'project.json'
    if not pj.exists():
        return {}
    try:
        return {x.get('id'): x.get('why', 'listened') for x in (C.read_json(pj).get('segments_ok') or []) if isinstance(x, dict)}
    except ValueError:
        return {}


def cmd_snap_audit(proj, edl, out, snap):
    clips = sorted({s['clip'] for s in edl})
    env, W = {}, {}
    for c in clips:
        wav = Path(proj) / 'work' / f'{c}.wav'
        if not wav.exists():
            C.fail(f'{wav} is missing.', 'Run ingest.py first.', out.json)
        env[c] = load_env(wav)
        W[c], kind = C.load_words(proj, c)
        if not W[c]:
            C.fail(f'No word timings for clip {c}.', f'Run: splice.py {proj} words   (or ingest.py for the fast pass).', out.json)
        if kind == 'fast':
            out.log(f'note: {c} has only fast (small.en) words; run `splice.py words` for precise cut points.')
    if snap:
        shutil.copy(Path(proj) / 'edl.json', Path(proj) / 'edl.bak.json')
    # phase 1: anchors and snapped edges
    info = []
    for s in edl:
        if not s.get('line', '').strip():
            info.append(None); continue
        e = env[s['clip']]
        fw, lw = anchor(W[s['clip']], s['line'], s['in'], s['out'], bool(s.get('lock_in')), bool(s.get('lock_out')))
        i_new, i_note = snap_in(e, fw['s'])
        o_new, o_note = snap_out(e, lw['e'])
        if not s.get('lock_out'):
            o_new, moved = settle_out(e, o_new, lw['e'])
            if moved:
                o_note = moved
        end_of_file = len(e.db) * HOP
        if o_note.startswith('TOUCHING') and end_of_file - o_new < 0.05:
            o_note = 'ok (end of file)'
        if not s.get('lock_in'):
            on = onset_after(e, i_new)
            if on is not None and on - i_new > DEAD_AIR:      # never start more than ~0.1 s before the voice
                i_new, i_note = round(on - 0.08, 3), 'ok (trimmed dead air)'
        would = []
        if not s.get('lock_in') and abs(i_new - s['in']) > MAX_MOVE:
            would.append(f"WOULD MOVE {s['id']}.in {s['in']:.2f} -> {i_new:.2f} (line start not found; check with env)")
            i_new, i_note = s['in'], 'kept (move too large)'
        if not s.get('lock_out') and abs(o_new - s['out']) > MAX_MOVE:
            would.append(f"WOULD MOVE {s['id']}.out {s['out']:.2f} -> {o_new:.2f} (line end not found; check with env)")
            o_new, o_note = s['out'], 'kept (move too large)'
        if s.get('lock_in'): i_new, i_note = s['in'], 'locked'
        if s.get('lock_out'): o_new, o_note = s['out'], 'locked'
        info.append({'fw': fw, 'lw': lw, 'in': i_new, 'out': o_new, 'i_note': i_note, 'o_note': o_note, 'would': would})
        if snap:
            s['in'], s['out'] = i_new, o_new
    # phase 2: neighbours in the same clip may not overlap or touch (B follows A in source)
    adj_notes = {}
    for k in range(1, len(edl)):
        A, B, ia, ib = edl[k - 1], edl[k], info[k - 1], info[k]
        if ia is None or ib is None or A['clip'] != B['clip'] or B['in'] <= A['in']:
            continue
        if B['in'] - A['out'] >= MIN_GAP:
            continue
        if snap:
            e = env[A['clip']]
            gap_a, gap_b = ia['lw']['e'], max(ia['lw']['e'] + 0.01, ib['fw']['s'])
            point = dip(e.db, gap_a, gap_b)
            if not B.get('lock_in'):
                B['in'] = round(min(max(B['in'], point + 0.02), ib['fw']['s'] - 0.005), 3)
            if not A.get('lock_out'):
                A['out'] = round(min(A['out'], B['in'] - MIN_GAP), 3)
        if B['in'] - A['out'] < MIN_GAP:
            adj_notes[k] = (f"EDGES TOUCH '{A['id']}' (out {A['out']:.2f}) and '{B['id']}' (in {B['in']:.2f}) in the source: "
                            f"there is no gap to cut in; merge them or pick other lines")
    # phase 3: notes
    ok_segs = load_segments_ok(proj)
    report, prev_last = [], None
    for k, s in enumerate(edl):
        if info[k] is None:
            report.append((s['id'], s['in'], s['out'], '?', '?', ['no `line` text: cannot anchor this segment'], s['clip'], []))
            continue
        e = env[s['clip']]; db = e.db; words = W[s['clip']]
        fw, lw, i_note, o_note = info[k]['fw'], info[k]['lw'], info[k]['i_note'], info[k]['o_note']
        a, b = s['in'], s['out']
        notes = []
        notes += info[k]['would']
        soft = []
        if not i_note.startswith(('ok', 'locked', 'kept')): notes.append('IN: ' + i_note)
        if not o_note.startswith(('ok', 'locked', 'kept')): notes.append('OUT: ' + o_note)
        on = onset_after(e, a)
        if on is not None and on - a > DEAD_AIR:
            notes.append(f"DEAD AIR: the in-point is {on - a:.2f} s before the first voiced frame ({on:.2f}); move `in` to about {on - 0.08:.2f}")
        if not s.get('lock_out') and b < lw['e'] + 0.03: notes.append(f"CLIPS LAST WORD '{lw['w']}' (ends {lw['e']:.2f}, out {b:.2f})")
        if not s.get('lock_in') and a > fw['s'] - 0.02: notes.append(f"CLIPS FIRST WORD '{fw['w']}' (starts {fw['s']:.2f}, in {a:.2f})")
        extra = [w['w'] for w in words_between(words, a, b) if w['e'] <= fw['s'] - 0.01 or w['s'] >= lw['e'] + 0.01]
        if extra:
            msg = f"EXTRA WORDS INSIDE THE CUT: {' '.join(extra)}"
            if s.get('lock_in') or s.get('lock_out'):
                soft.append('note (locked): ' + msg + ' (Whisper may have stretched words; listen once and add the segment to project.json segments_ok to silence this)')
            else:
                notes.append(msg)
        ia, ib = int(a / HOP), int(b / HOP)
        if ia < len(db) and db[ia] > e.speech: notes.append(f'IN LANDS ON VOICE ({db[ia]:.0f} dB): starts mid-sound')
        if ib < len(db) - 5 and db[ib] > e.speech: notes.append(f'OUT LANDS ON VOICE ({db[ib]:.0f} dB): clips a sound')
        first = norm(fw['w'])
        if prev_last and first == prev_last: notes.append(f"REPEAT ACROSS JOIN: '{first}' ends the previous segment and starts this one")
        if k in adj_notes: notes.append(adj_notes[k])
        prev_last = norm(lw['w'])
        why = ok_segs.get(s['id'])
        if why is not None and notes:
            soft += [f'accepted ({why}): ' + n for n in notes]
            notes = []
        report.append((s['id'], a, b, fw['w'], lw['w'], notes, s['clip'], soft))
    if snap:
        C.write_json(Path(proj) / 'edl.json', edl)
    bad = 0
    for sid, a, b, f, l, notes, clip, soft in report:
        bad += bool(notes)
        txt = f"{'FIX ' if notes else 'ok  '}{sid:6} {a:8.2f}-{b:8.2f}  '{f}' .. '{l}'"
        if soft:
            txt += '\n        ' + '\n        '.join(soft)
        if notes:
            txt += '\n        ' + '\n        '.join(notes)
            txt += f"\n        look at the sound: splice.py {proj} env {clip} {max(0, a - 0.6):.2f} {a + 0.6:.2f}   (in)   |   env {clip} {b - 0.6:.2f} {b + 0.6:.2f}   (out)"
        out.log(txt)
    out.log(f'\n{len(report)} segments, {bad} flagged')
    out.result({'ok': True, 'command': 'snap' if snap else 'audit', 'segments': len(report), 'flagged': bad,
                'items': [{'id': r[0], 'in': r[1], 'out': r[2], 'first': r[3], 'last': r[4], 'notes': r[5], 'soft_notes': r[7]} for r in report]})


# --------------------------------------------------------------------------------------------- joins
def _match(tok, heard, last=False):
    """index of the best fuzzy match of tok in the heard tokens (the last good one when last=True), or -1"""
    best, bi = 0.0, -1
    for i, h in enumerate(heard):
        r = difflib.SequenceMatcher(None, tok, h).ratio()
        if r >= 0.72 and (r > best or (last and r >= best - 0.05)):
            best, bi = max(r, best), i
    return bi


def load_waivers(proj):
    pj = Path(proj) / 'project.json'
    if not pj.exists():
        return {}
    try:
        items = C.read_json(pj).get('joins_ok', []) or []
    except ValueError:
        return {}
    return {(w.get('a'), w.get('b')): w.get('why', 'waived') for w in items if isinstance(w, dict)}


def cmd_joins(proj, out, strict=False):
    """Verdict per join = energy + text.
       energy at the join (40 ms each side): voice (above the clip's voice level) / sound (above quiet, below voice) / quiet
       flagged = voice at the join (a word may be clipped) or a repeated word across it
       check   = the heard text disagrees AND there is sound at the join
       ok      = everything else; a text mismatch over a quiet join is Whisper's mistake ("ok (text mismatch only)")
       project.json "joins_ok": [{"a","b","why"}] waives a join (verdict ok, waived true)."""
    import numpy as np
    chk = Path(proj) / 'work' / 'aroll_check.wav'
    aroll = Path(proj) / 'assets' / 'aroll.mp4'
    if not aroll.exists():
        C.fail('assets/aroll.mp4 does not exist yet.', 'Run assemble.py first.', out.json)
    C.ffmpeg(['-i', aroll, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', chk])
    env = load_env(chk)
    quiet_db = env.floor + BREATH_DB
    segs = C.read_json(Path(proj) / 'segments.json')
    wf = Path(proj) / 'words.json'
    ws = C.read_json(wf) if wf.exists() else C.cut_words(proj, segs)
    audio = (read_wav(chk)[0] / 32768.0).astype(np.float32)
    total = len(audio) / 16000
    prompt = names_prompt(proj)
    waivers = load_waivers(proj)
    pre = []
    for k in range(1, len(segs)):
        t = segs[k]['frame'] / 30
        i = int(t / HOP)
        before, after = float(env.db[max(0, i - 4):i].max()), float(env.db[i:i + 4].max())
        near = [w for w in ws if abs(w['start'] - t) < 0.6 or abs(w.get('end', w['start']) - t) < 0.6]
        toks = [norm(w['text']) for w in near]
        rep = [a for a, b in zip(toks, toks[1:]) if a and a == b]
        top = max(before, after)
        state = 'voice' if top > env.speech else ('sound' if top > quiet_db else 'quiet')
        notes = []
        if before > env.speech: notes.append(f'voice right before the join ({before:.0f} dB): a word may be clipped')
        if after > env.speech: notes.append(f'voice right after the join ({after:.0f} dB): a word may start clipped')
        if rep: notes.append(f'repeated word across the join: {rep}')
        pre.append({'k': k, 't': t, 'notes': notes, 'rep': bool(rep), 'state': state, 'before': before, 'after': after})
    model = C.whisper_model(PRECISE_MODEL, WORKERS)

    def solo(item):
        a, b = max(0.0, item['t'] - JOIN_WIN / 2), min(total, item['t'] + JOIN_WIN / 2)
        ws_, dropped_ = refine_words(transcribe_window(model, audio, a, b, prompt, words=True), env)
        cw = [{'text': w['w'], 'start': w['s'], 'end': w['e']} for w in ws_]
        near_segs = [sg for sg in segs if abs(sg['frame'] / 30 - item['t']) < 2.0 or abs((sg['frame'] + sg['frames']) / 30 - item['t']) < 2.0]
        cw, ph_ = drop_join_phantoms(cw, near_segs, env)
        return ' '.join(w['text'] for w in cw).strip(), dropped_ + ph_
    out.log(f'transcribing {len(pre)} joins alone ({JOIN_WIN} s each, {PRECISE_MODEL}) ...')
    with ThreadPoolExecutor(WORKERS) as ex:
        solos = list(ex.map(solo, pre))
    heards = [h for h, _ in solos]
    phantoms = [d for _, d in solos]
    joins, n_flag, n_check, n_waived = [], 0, 0, 0
    for p, heard, ph in zip(pre, heards, phantoms):
        k, t = p['k'], p['t']
        a_id, b_id = segs[k - 1]['id'], segs[k]['id']
        htoks = [norm(x) for x in heard.split() if norm(x)]
        ptoks = [norm(x) for x in segs[k - 1].get('line', '').split() if norm(x)]
        ntoks = [norm(x) for x in segs[k].get('line', '').split() if norm(x)]
        exp_prev, exp_next = ptoks[-2:], ntoks[:2]
        tnotes = []
        if ptoks and ntoks:
            ip = _match(ptoks[-1], htoks, last=True)
            inx = _match(ntoks[0], htoks[ip + 1:] if ip >= 0 else htoks)
            if ip < 0: tnotes.append(f"heard text lacks the last word of the previous line '{ptoks[-1]}'")
            if inx < 0: tnotes.append(f"heard text lacks the first word of the next line '{ntoks[0]}' right after the join")
            elif ip >= 0 and inx > 0: tnotes.append('extra words heard between the two sides of the join')
        energy_bad = p['state'] == 'voice' or p['rep']
        if energy_bad:
            verdict = 'flagged'
        elif tnotes and p['state'] == 'sound':
            verdict = 'check'
        else:
            verdict = 'ok'
        notes = p['notes'] + tnotes
        if tnotes and verdict == 'ok':
            notes = p['notes'] + ['text mismatch only (the join is quiet, so this is most likely Whisper mishearing): ' + '; '.join(tnotes)]
        waived = False
        why = waivers.get((a_id, b_id))
        if why is not None and verdict != 'ok':
            verdict, waived = 'ok', True
        n_flag += verdict == 'flagged'; n_check += verdict == 'check'; n_waived += waived
        label = {'flagged': 'FIX ', 'check': 'CHECK', 'ok': 'ok  '}[verdict]
        out.log(f"{label} {a_id:>6} | {b_id:<6} at {t:6.2f}s  " + ('(waived: ' + why + ') ' if waived else '') + '; '.join(notes))
        out.log(f"       expected ...{' '.join(exp_prev)} | {' '.join(exp_next)}...   heard: \"{heard}\"" +
                (f"   (dropped phantom: {', '.join(f'{t} @{at}' for t, at in ph)})" if ph else ''))
        joins.append({'a': a_id, 'b': b_id, 't': round(t, 3), 'verdict': verdict, 'flagged': verdict == 'flagged',
                      'check': verdict == 'check', 'waived': waived, 'waiver_reason': why if waived else None,
                      'energy': {'state': p['state'], 'before_db': round(p['before'], 1), 'after_db': round(p['after'], 1),
                                 'voice_db': round(env.speech, 1), 'quiet_db': round(quiet_db, 1)},
                      'notes': notes, 'heard': heard, 'dropped_phantoms': [f'{t} @{at}' for t, at in ph],
                      'expected': {'prev': exp_prev, 'next': exp_next}, 'expected_prev': exp_prev, 'expected_next': exp_next})
    out.log(f'\n{len(segs) - 1} joins: {n_flag} flagged, {n_check} to check, {n_waived} waived')
    res = {'total': len(segs) - 1, 'flagged': n_flag, 'check': n_check, 'waived': n_waived, 'joins': joins}
    C.write_json(Path(proj) / 'work' / 'joins.json', res)
    out.result({'ok': True, 'command': 'joins', **res})
    if strict and n_flag:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description='Snap EDL cut points to silence and audit joins.')
    ap.add_argument('project')
    ap.add_argument('cmd', choices=['words', 'snap', 'audit', 'joins', 'env'])
    ap.add_argument('args', nargs='*', help='env: <clip> <t0> <t1>')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--full', action='store_true', help='words: medium.en over the whole clip (default for clips up to 6 min)')
    ap.add_argument('--windows', action='store_true', help='words: only windows around the cut points (default for longer clips)')
    ap.add_argument('--strict', action='store_true', help='joins: exit 1 when a join is flagged')
    ap.add_argument('--step', type=float, default=0.02, help='env: seconds per row')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    need = {'joins': ['segments.json'], 'env': []}.get(a.cmd, ['edl.json'])
    proj = C.need_project(a.project, need, a.json)
    try:
        if a.cmd == 'env':
            if len(a.args) != 3:
                C.fail('env needs a clip and a time range.', 'Example: splice.py <project> env c1 12.0 13.5 --step 0.02', a.json)
            return cmd_env(proj, a.args[0], float(a.args[1]), float(a.args[2]), a.step, out)
        if a.cmd == 'joins':
            return cmd_joins(proj, out, a.strict)
        edl = C.read_json(proj / 'edl.json')
        if a.cmd == 'words':
            return cmd_words(proj, edl, out, 'full' if a.full else ('windows' if a.windows else 'auto'))
        return cmd_snap_audit(proj, edl, out, a.cmd == 'snap')
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        C.fail(str(e), 'Check the project folder and that ffmpeg is installed (run doctor.py).', a.json)


if __name__ == '__main__':
    main()
