"""Caption words for the finished cut: words.json (cut time) = Whisper on the FINAL audio + your caption fixes.

Usage:
  words.py <project> build [--force]        medium.en on the final audio (whole pass, cached by AUDIO hash) -> words.auto.json;
                                            then the EDL `line` text of every segment is aligned onto those word times (line
                                            words win spelling / punctuation / missing words; Whisper words the line has no
                                            match for are kept; project.json "captions_from": "whisper" turns this off);
                                            then caption_fixes.json on top -> words.json
  words.py <project> fix "<wrong>" "<right>" [--at SEC | --all]
                                            replace a word or phrase ("" deletes) and rebuild. A pattern with punctuation
                                            matches exactly ("level." is not "level"); without punctuation it ignores it.
                                            Every place changed is printed with 4 words of context. More than one match is
                                            refused unless you pass --at (one place) or --all.
  words.py <project> check                  every difference between words.json and what Whisper heard
  words.py <project> script <file.txt>        align a corrected plain-text script to the audio timing (kept as
                                            captions_script.txt, re-applied on every build), then the fixes on top
  words.py <project> pin <seconds> "<text>"   replace the word at that cut time
  words.py <project> list                     print words.json with times (to find what to fix)
  words.py <project> time <seconds> <start> [<end>]
                                            move the word nearest that cut time to start (and end) at the given times,
                                            text unchanged; for a word Whisper timed late or early (read the energy first:
                                            a caption must appear when the word is heard). Kept in caption_fixes.json.
All commands take --json. assemble.py calls `build` for you (skip with --no-words) and never edits words.json itself.

Files (project root):  words.auto.json  [{text,start,end}] raw Whisper words (zero-length / stacked words repaired)
                       caption_fixes.json  [{"from":"physician","to":"physician,"}, {"at":12.3,"text":"Ozempic"}]
                       words.json  what the template reads
Proper nouns: put one per line in ~/.reel-room/names.txt or <project>/names.txt; they are fed to Whisper as a spelling hint.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MODEL = 'medium.en'
TRAIL = re.compile(r"[^\w']+$")


# ---------------------------------------------------------------------------------------------- repair
def _weights(texts):
    return [max(1, len(re.sub(r'\W', '', t))) for t in texts]


def spread(texts, t0, t1):
    """give each text a slice of [t0,t1] proportional to its length"""
    w = _weights(texts)
    tot, cur, out = sum(w), t0, []
    for t, x in zip(texts, w):
        e = cur + (t1 - t0) * x / tot
        out.append({'text': t, 'start': round(cur, 3), 'end': round(e, 3)})
        cur = e
    return out


def sanitize(ws):
    """drop empty / zero-length-at-the-end words, un-stack words that share one timestamp, make times monotonic"""
    ws = [{'text': str(w['text']).strip(), 'start': float(w['start']), 'end': float(w['end'])} for w in ws if str(w['text']).strip()]
    ws.sort(key=lambda w: (w['start'], w['end']))
    out, i, n = [], 0, len(ws)
    degenerate = lambda k: ws[k]['end'] - ws[k]['start'] < 0.02  # noqa: E731
    while i < n:
        j = i + 1
        while j < n and (abs(ws[j]['start'] - ws[i]['start']) < 0.005 or (degenerate(j - 1) and degenerate(j))):
            j += 1
        if degenerate(i) and j == i + 1:           # a lone zero-length word: give it a short slice before the next word
            nxt = ws[j]['start'] if j < n else ws[i]['start'] + 0.15
            end = min(max(ws[i]['start'] + 0.12, ws[i]['end']), nxt) if nxt > ws[i]['start'] + 0.04 else ws[i]['start'] + 0.04
            out.append({**ws[i], 'end': round(end, 3)})
        elif j - i > 1:                            # stacked group: spread over its real span
            t0 = ws[i]['start']
            t1 = max(max(w['end'] for w in ws[i:j]), (ws[j]['start'] if j < n else t0))
            if t1 - t0 < 0.08 * (j - i):
                t1 = ws[j]['start'] if j < n and ws[j]['start'] - t0 >= 0.04 * (j - i) else t0 + 0.12 * (j - i)
            out += spread([w['text'] for w in ws[i:j]], t0, t1)
        else:
            out.append({**ws[i], 'start': round(ws[i]['start'], 3), 'end': round(ws[i]['end'], 3)})
        i = j
    for a, b in zip(out, out[1:]):                 # monotonic, no overlaps
        if b['start'] < a['end']:
            a['end'] = round(max(a['start'] + 0.02, b['start']), 3)
        if b['start'] < a['start'] + 0.02:
            b['start'] = round(a['start'] + 0.02, 3)
            b['end'] = max(b['end'], b['start'] + 0.02)
    return out


# ---------------------------------------------------------------------------------------------- build
def final_wav(proj):
    """16 kHz mono wav of the final cut's audio (re-extracted when aroll.mp4 is newer)"""
    wav = Path(proj) / 'work' / 'aroll16.wav'
    aroll = Path(proj) / 'assets' / 'aroll.mp4'
    if not aroll.exists():
        C.fail('assets/aroll.mp4 does not exist yet.', 'Run assemble.py first.', False)
    if not wav.exists() or wav.stat().st_mtime < aroll.stat().st_mtime:
        C.ffmpeg(['-i', aroll, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav])
    return wav


def repair(proj, ws, out):
    """trim words to the voiced energy of the final audio, drop phantoms ("dropped phantom: If @23.6"), un-stack"""
    from splice import load_env, refine_words
    env = load_env(final_wav(proj))
    sj = Path(proj) / 'segments.json'
    segs = C.read_json(sj) if sj.exists() else []
    from splice import drop_join_phantoms, line_tokens, matches_line

    def protect(w):   # a word that matches the line the speaker was cutting to is never dropped
        return bool(segs) and matches_line(w['text'], line_tokens(segs, (w['start'] + w['end']) / 2))
    ws, dropped = refine_words(ws, env, 'start', 'end', 'text', protect=protect)
    possible = []
    if segs:
        ws, ph = drop_join_phantoms(ws, segs, env, possible=possible)
        dropped += ph
    for t, at in possible:
        out.log(f'  possible phantom: {t} @{at} (keep; fix with words.py {proj} fix "{t}" "" if wrong)')
    for t, at in dropped:
        out.log(f'  dropped phantom: {t} @{at}')
    return sanitize(ws), dropped


def transcribe_final(proj, out, force=False):
    wav = final_wav(proj)
    prompt = C.names_prompt(proj)
    # keyed on the AUDIO only (a grade or other picture change must not trigger another medium.en pass)
    key = C.hashlib.blake2b(wav.read_bytes() + f'|{prompt}|{MODEL}'.encode(), digest_size=8).hexdigest()
    cf = C.CACHE / 'words_final' / f'{key}.json'
    if cf.exists() and not force:
        out.log('final-audio transcript: cached (audio unchanged)')
        return C.read_json(cf)
    import numpy as np
    from splice import read_wav
    audio = (read_wav(wav)[0] / 32768.0).astype(np.float32)
    out.log(f'transcribing the final cut ({len(audio) / 16000:.0f} s) with {MODEL} ...')
    t0 = time.time()
    model = C.whisper_model(MODEL)
    segs, _ = model.transcribe(audio, language='en', word_timestamps=True, beam_size=5, temperature=0.0,
                               condition_on_previous_text=False, initial_prompt=prompt,
                               hallucination_silence_threshold=1.5)
    ws = [{'text': w.word.strip(), 'start': w.start, 'end': w.end} for s in segs for w in (s.words or [])]
    C.write_json(cf, ws, indent=None)          # cache the raw transcript; energy repair is applied on every build
    out.log(f'  {len(ws)} words in {time.time() - t0:.0f}s')
    return ws


# ---------------------------------------------------------------------------------------------- fixes
PUNCT = re.compile(r"[^\w']")


def _pat_tokens(s):
    return str(s).split()


def _tok_eq(word_text, pat):
    """a pattern token with punctuation must match the word EXACTLY (case-insensitive: "level." is not "level");
    a plain pattern token matches the word with its punctuation ignored ("drink" matches "drink.")"""
    if PUNCT.search(pat):
        return word_text.strip().lower() == pat.lower()
    return C.norm(word_text) == C.norm(pat)


def find_matches(ws, pattern):
    pat = _pat_tokens(pattern)
    out, i = [], 0
    while pat and i <= len(ws) - len(pat):
        if all(_tok_eq(ws[i + k]['text'], p) for k, p in enumerate(pat)):
            out.append(i); i += len(pat)
        else:
            i += 1
    return out


def _with_trailing(new_tokens, old_last):
    """keep the punctuation Whisper wrote after the last word unless the replacement brings its own"""
    if not new_tokens:
        return new_tokens
    m = TRAIL.search(old_last)
    if m and not TRAIL.search(new_tokens[-1]):
        new_tokens = new_tokens[:-1] + [new_tokens[-1] + m.group(0)]
    return new_tokens


def _replace_span(ws, i, j, new_text):
    """replace ws[i:j] with the words of new_text, keeping timing (1:1 when counts match, else spread over the span)"""
    old = ws[i:j]
    new = _with_trailing(new_text.split(), old[-1]['text'])
    if not new:
        return ws[:i] + ws[j:]
    if len(new) == len(old):
        rep = [{**o, 'text': t} for o, t in zip(old, new)]
    else:
        rep = spread(new, old[0]['start'], old[-1]['end'])
    return ws[:i] + rep + ws[j:]


def context(ws, i, j, n=4):
    pre = ' '.join(w['text'] for w in ws[max(0, i - n):i])
    post = ' '.join(w['text'] for w in ws[j:j + n])
    return f"{pre} [{' '.join(w['text'] for w in ws[i:j])}] {post}".strip()


def pick_matches(ms, f, plen, ws):
    """which matches a stored fix applies to: the one near `at`, or all (a fix made with --all, or an old one)"""
    if 'at' in f:
        near = [m for m in ms if abs(ws[m]['start'] - float(f['at'])) <= 0.6 or ws[m]['start'] <= float(f['at']) <= ws[min(len(ws) - 1, m + plen - 1)]['end']]
        return near[:1] if near else []
    return ms


def apply_fixes(ws, fixes):
    log = []
    ws = [dict(w) for w in ws]
    for f in fixes:                                     # pins first (they refer to the auto timeline)
        if 'at' in f and 'text' in f and 'from' not in f and 'start' not in f:
            if not ws:
                continue
            k = min(range(len(ws)), key=lambda x: abs((ws[x]['start'] + ws[x]['end']) / 2 - float(f['at'])))
            if abs((ws[k]['start'] + ws[k]['end']) / 2 - float(f['at'])) <= 0.6:
                log.append(f"pin @{f['at']}: {context(ws, k, k + 1)} -> '{f['text']}'")
                ws = _replace_span(ws, k, k + 1, str(f['text']))
            else:
                log.append(f"pin @{f['at']}: no word within 0.6 s")
    for f in fixes:
        if 'from' not in f:
            continue
        plen = len(_pat_tokens(f['from']))
        if not plen:
            continue
        ms = pick_matches(find_matches(ws, f['from']), f, plen, ws)
        if len(ms) > 1 and 'at' not in f and not f.get('all'):
            log.append(f"fix '{f['from']}' matches {len(ms)} places and was made without --all: applied to all (add --at <sec> to target one)")
        for m in reversed(ms):                          # right to left keeps earlier indices valid
            log.append(f"fix @{ws[m]['start']:.2f}: {context(ws, m, m + plen)}  ->  '{f.get('to', '')}'")
            ws = _replace_span(ws, m, m + plen, str(f.get('to', '')))
        if not ms:
            log.append(f"fix '{f['from']}' -> '{f.get('to', '')}': no match (already right, or the audio changed)")
    for f in fixes:                                     # retimes last: they move a word's start/end, text unchanged
        if 'at' not in f or 'start' not in f or not ws:
            continue
        k = min(range(len(ws)), key=lambda x: abs(ws[x]['start'] - float(f['at'])))
        if abs(ws[k]['start'] - float(f['at'])) > 0.6:
            log.append(f"time @{f['at']}: no word within 0.6 s")
            continue
        lo = ws[k - 1]['start'] + 0.02 if k else 0.0
        hi = ws[k + 1]['start'] if k + 1 < len(ws) else float('inf')
        st = min(max(float(f['start']), lo), hi - 0.02)
        en = min(max(float(f.get('end', ws[k]['end'])), st + 0.04), hi if k + 1 < len(ws) else float('inf'))
        log.append(f"time @{f['at']}: '{ws[k]['text']}' {ws[k]['start']:.2f}-{ws[k]['end']:.2f} -> {st:.2f}-{en:.2f}")
        if k and ws[k - 1]['end'] > st:
            ws[k - 1] = {**ws[k - 1], 'end': round(st, 3)}
        ws[k] = {**ws[k], 'start': round(st, 3), 'end': round(en, 3)}
    return ws, log


# ---------------------------------------------------------------------------------------------- script alignment
def align_script(auto, script_text):
    """give every token of a corrected script a time from the Whisper words it matches; fill the rest by interpolation"""
    toks = script_text.split()
    a = [C.norm(w['text']) for w in auto]
    b = [C.norm(t) for t in toks]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(j2 - j1):
                out.append({'text': toks[j1 + k], 'start': auto[i1 + k]['start'], 'end': auto[i1 + k]['end']})
        elif j2 > j1:
            if i2 > i1:
                t0, t1 = auto[i1]['start'], auto[i2 - 1]['end']
            else:
                t0 = auto[i1 - 1]['end'] if i1 > 0 else 0.0
                t1 = auto[i1]['start'] if i1 < len(auto) else t0 + 0.12 * (j2 - j1)
                if t1 - t0 < 0.05 * (j2 - j1):
                    t1 = t0 + 0.08 * (j2 - j1)
            out += spread(toks[j1:j2], t0, t1)
    return sanitize(out)


# ---------------------------------------------------------------------------------------------- lines as the caption script
FUZZY = 0.75


def _sim(a, b):
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    return r if r >= FUZZY else 0.0


def _pair(a, b):
    """order-preserving best pairing of two token lists (LCS with fuzzy equality). Returns [(i, j)]"""
    n, m = len(a), len(b)
    S = [[_sim(a[i], b[j]) for j in range(m)] for i in range(n)]
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            D[i][j] = max(D[i + 1][j], D[i][j + 1], D[i + 1][j + 1] + S[i][j] if S[i][j] else 0)
    out, i, j = [], 0, 0
    while i < n and j < m:
        if S[i][j] and abs(D[i][j] - (D[i + 1][j + 1] + S[i][j])) < 1e-9:
            out.append((i, j)); i += 1; j += 1
        elif D[i + 1][j] >= D[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def align_segment(sw, toks, notes, sid):
    """sw = Whisper words of one segment, toks = the words of its EDL line. Line words win spelling, punctuation and missing
    words; Whisper words the line has no match for are kept."""
    a = [C.norm(w['text']) for w in sw]
    b = [C.norm(t) for t in toks]
    pairs = _pair(a, b) + [(len(sw), len(toks))]
    out, pi, pj = [], 0, 0
    for i, j in pairs:
        wr, lr = sw[pi:i], toks[pj:j]
        if wr and lr:
            if len(wr) == len(lr):
                out += [{**w, 'text': t} for w, t in zip(wr, lr)]
            elif len(wr) - len(lr) <= 1:
                out += spread(lr, wr[0]['start'], wr[-1]['end'])
            else:
                out += wr
                notes.append(f"{sid}: line and audio differ a lot here ('{' '.join(lr)}' vs '{' '.join(w['text'] for w in wr)}'); kept the audio words")
        elif lr:                                           # in the line, not heard: place inside the gap
            t0 = out[-1]['end'] if out else (sw[0]['start'] if sw else 0.0)
            t1 = sw[i]['start'] if i < len(sw) else t0 + 0.12 * len(lr)
            if t1 - t0 < 0.05 * len(lr):
                t1 = t0 + 0.08 * len(lr)
            out += spread(lr, t0, t1)
        else:
            out += wr                                      # heard, not in the line: keep
        if i < len(sw) and j < len(toks):
            out.append({**sw[i], 'text': toks[j]})
        pi, pj = i + 1, j + 1
    return out


def align_lines(auto, segs, out):
    """EDL `line` text is the default caption script: align each line to the Whisper words inside that segment's cut range"""
    used, res, notes = set(), [], []
    for sg in segs:
        f0, f1 = sg['frame'] / C.FPS, (sg['frame'] + sg['frames']) / C.FPS
        idx = [k for k, w in enumerate(auto) if f0 <= (w['start'] + w['end']) / 2 < f1]
        used.update(idx)
        sw = [auto[k] for k in idx]
        toks = sg.get('line', '').split()
        res += align_segment(sw, toks, notes, sg['id']) if toks and sw else sw
    res += [w for k, w in enumerate(auto) if k not in used]
    for n in notes:
        out.log('  note: ' + n)
    return sanitize(sorted(res, key=lambda w: w['start']))


def stage_words(proj, out, force=False):
    """words after repair + caption script (lines / script file), BEFORE caption_fixes. Returns (words, auto, dropped)"""
    proj = Path(proj)
    auto, dropped = repair(proj, transcribe_final(proj, out, force), out)
    C.write_json(proj / 'words.auto.json', auto, indent=None)
    ws = auto
    sc = proj / 'captions_script.txt'
    pj = C.read_json(proj / 'project.json') if (proj / 'project.json').exists() else {}
    if sc.exists() and sc.read_text(encoding='utf-8').strip():
        ws = align_script(auto, sc.read_text(encoding='utf-8'))
        out.log('captions: aligned captions_script.txt to the audio')
    elif pj.get('captions_from') != 'whisper' and (proj / 'segments.json').exists():
        ws = align_lines(auto, C.read_json(proj / 'segments.json'), out)
        out.log('captions: EDL line text aligned to the audio (project.json "captions_from": "whisper" turns this off)')
    else:
        out.log('captions: Whisper words as heard')
    return ws, auto, dropped


# Fixes made "at" a cut time also store where that moment is in the SOURCE clip ("src"), because a snip or nudge
# earlier in the reel moves every later cut time. On each build the cut time is re-derived from segments.json.
def _segs(proj):
    sj = Path(proj) / 'segments.json'
    return C.read_json(sj) if sj.exists() else []


def anchor_src(proj, t):
    """cut time -> {"clip","t"} source moment, or None when segments.json is missing."""
    for sg in _segs(proj):
        t0 = sg['frame'] / 30.0
        if t0 - 1e-6 <= t < t0 + sg['frames'] / 30.0 + 1e-6:
            return {'clip': sg['clip'], 't': round(sg.get('src_in', sg['in']) + (t - t0), 3)}
    return None


def resolve_fixes(proj, fixes):
    """Shift every src-anchored fix to its cut time in the CURRENT cut. Fixes whose moment was cut out are skipped."""
    segs, out, log = _segs(proj), [], []
    for f in fixes:
        src = f.get('src')
        if not (src and 'at' in f and segs):
            out.append(f)
            continue
        hit = None
        for sg in segs:
            a, b = sg.get('src_in', sg['in']), sg.get('src_out', sg['out'])
            if sg['clip'] == src.get('clip') and a - 0.05 <= float(src['t']) <= b + 0.05:
                hit = sg['frame'] / 30.0 + (float(src['t']) - a)
                break
        if hit is None:
            log.append(f"fix @{f['at']} skipped: that moment is no longer in the cut")
            continue
        d = round(hit - float(f['at']), 3)
        g = dict(f, at=round(float(f['at']) + d, 3))
        for k in ('start', 'end'):
            if k in g:
                g[k] = round(float(g[k]) + d, 3)
        if abs(d) > 1e-3:
            log.append(f"fix @{f['at']} follows the cut to {g['at']}")
        out.append(g)
    return out, log


def rebuild(proj, out, force=False, emit=True):
    proj = Path(proj)
    ws, auto, dropped = stage_words(proj, out, force)
    fx = proj / 'caption_fixes.json'
    fixes = C.read_json(fx) if fx.exists() else []
    rfixes, rlog = resolve_fixes(proj, fixes)
    ws, log = apply_fixes(ws, rfixes)
    log = rlog + log
    for line in log:
        out.log('  ' + line)
    C.write_json(proj / 'words.json', ws, indent=None)
    out.log(f'wrote words.json ({len(ws)} words, {len(fixes)} fixes). To correct a word: words.py {proj} fix "<wrong>" "<right>" [--at SEC | --all]')
    if emit:
        out.result({'ok': True, 'command': 'build', 'words': len(ws), 'fixes': len(fixes), 'fix_log': log,
                    'dropped_phantoms': [f'{t} @{at}' for t, at in dropped], 'words_json': str(proj / 'words.json')})
    return ws


def build(proj, out=None, force=False):
    """called by assemble.py"""
    return rebuild(proj, out or C.Out(False), force, emit=False)


class _Quiet(C.Out):
    def __init__(self):
        super().__init__(False)

    def log(self, *a):
        pass


def cmd_fix(proj, out, args, at, all_):
    fx = proj / 'caption_fixes.json'
    fixes = C.read_json(fx) if fx.exists() else []
    wrong, right = args
    ws, _, _ = stage_words(proj, _Quiet())                # quiet: the build that follows prints the details
    ws, _ = apply_fixes(ws, resolve_fixes(proj, [f for f in fixes if not (f.get('from', '').lower() == wrong.lower() and ('at' in f) == (at is not None))])[0])
    ms = find_matches(ws, wrong)
    plen = len(_pat_tokens(wrong))
    if not ms:
        C.fail(f'"{wrong}" does not appear in the captions.',
               f'Run words.py {proj} list to see the words. Add punctuation if you mean a specific one ("level." is not "level").', out.json)
    if at is not None:
        near = [m for m in ms if abs(ws[m]['start'] - at) <= 0.6 or ws[m]['start'] <= at <= ws[min(len(ws) - 1, m + plen - 1)]['end']]
        if not near:
            C.fail(f'No "{wrong}" near {at}s.', 'Matches are at: ' + ', '.join(f"{ws[m]['start']:.2f}s" for m in ms), out.json)
    elif len(ms) > 1 and not all_:
        places = '\n'.join(f"  {ws[m]['start']:6.2f}s  {context(ws, m, m + plen)}" for m in ms)
        C.fail(f'"{wrong}" matches {len(ms)} places:\n{places}', 'Pick one with --at <seconds>, or change all of them with --all.', out.json)
    entry = {'from': wrong, 'to': right}
    if at is not None:
        entry['at'] = at
        src = anchor_src(proj, at)
        if src:
            entry['src'] = src
    if all_:
        entry['all'] = True
    fixes = [f for f in fixes if not (f.get('from', '').lower() == wrong.lower() and f.get('at') == at)] + [entry]
    C.write_json(fx, fixes)
    rebuild(proj, out)


def cmd_check(proj, out):
    """compare words.json with what Whisper heard (words.auto.json): every difference, for a quick review"""
    wj, aj = proj / 'words.json', proj / 'words.auto.json'
    if not wj.exists() or not aj.exists():
        C.fail('words.json / words.auto.json are missing.', f'Run: words.py {proj} build', out.json)
    ws, au = C.read_json(wj), C.read_json(aj)
    a, b = [C.norm(w['text']) for w in au], [C.norm(w['text']) for w in ws]
    diffs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'equal':
            t = (au[i1]['start'] if i1 < len(au) else (au[-1]['end'] if au else 0.0))
            diffs.append({'t': round(t, 2), 'heard': ' '.join(w['text'] for w in au[i1:i2]), 'caption': ' '.join(w['text'] for w in ws[j1:j2])})
    for d in diffs:
        out.log(f"  {d['t']:6.2f}s  heard '{d['heard']}'  caption '{d['caption']}'")
    out.log(f'{len(diffs)} difference(s) between the captions and what Whisper heard (words only, punctuation ignored)')
    out.result({'ok': True, 'command': 'check', 'differences': diffs})


def main():
    ap = argparse.ArgumentParser(description='Caption words: build, fix, script, pin, list.')
    ap.add_argument('project')
    ap.add_argument('cmd', choices=['build', 'fix', 'script', 'pin', 'list', 'check', 'time'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--force', action='store_true', help='build: ignore the cached transcript')
    ap.add_argument('--at', type=float, help='fix: only the occurrence at this cut time (seconds)')
    ap.add_argument('--all', action='store_true', help='fix: change every occurrence')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    proj = C.need_project(a.project, [], a.json)
    fx = proj / 'caption_fixes.json'
    if a.cmd == 'fix':
        if len(a.args) != 2:
            C.fail('fix needs two values.', 'Example: words.py <project> fix "Ozempick" "Ozempic" [--at 12.3 | --all]', a.json)
        cmd_fix(proj, out, a.args, a.at, a.all)
    elif a.cmd == 'check':
        cmd_check(proj, out)
    elif a.cmd == 'pin':
        if len(a.args) != 2:
            C.fail('pin needs a time and a text.', 'Example: words.py <project> pin 12.3 "Ozempic"', a.json)
        fixes = C.read_json(fx) if fx.exists() else []
        e = {'at': float(a.args[0]), 'text': a.args[1]}
        src = anchor_src(proj, e['at'])
        fixes.append(dict(e, src=src) if src else e)
        C.write_json(fx, fixes)
        rebuild(proj, out)
    elif a.cmd == 'time':
        if len(a.args) not in (2, 3):
            C.fail('time needs the word time, a new start and optionally a new end.',
                   'Example: words.py <project> time 47.29 46.98 47.28', a.json)
        fixes = C.read_json(fx) if fx.exists() else []
        e = {'at': float(a.args[0]), 'start': float(a.args[1])}
        if len(a.args) == 3:
            e['end'] = float(a.args[2])
        src = anchor_src(proj, e['at'])
        if src:
            e['src'] = src
        fixes = [f for f in fixes if not ('start' in f and abs(float(f['at']) - e['at']) < 1e-3)] + [e]
        C.write_json(fx, fixes)
        rebuild(proj, out)
    elif a.cmd == 'script':
        if len(a.args) != 1 or not Path(a.args[0]).expanduser().is_file():
            C.fail('script needs a plain-text file.', 'Example: words.py <project> script ~/script.txt', a.json)
        (proj / 'captions_script.txt').write_text(Path(a.args[0]).expanduser().read_text(encoding='utf-8'), encoding='utf-8')
        rebuild(proj, out)
    elif a.cmd == 'list':
        wj = proj / 'words.json'
        if not wj.exists():
            C.fail('words.json does not exist yet.', f'Run: words.py {proj} build', a.json)
        ws = C.read_json(wj)
        for i, w in enumerate(ws):
            out.log(f"{i:4} {w['start']:7.2f}-{w['end']:7.2f}  {w['text']}")
        out.result({'ok': True, 'command': 'list', 'words': ws})
    else:
        rebuild(proj, out, a.force)


if __name__ == '__main__':
    main()
