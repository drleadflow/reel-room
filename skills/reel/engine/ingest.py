"""Ingest raw clips into a Reel Room project.

Usage: ingest.py <project> <clips... | folder> [--newest N] [--json] [--model small.en] [--no-sheet]
  - clips can be files and/or folders (folders are scanned for video files; --newest N keeps the N newest by modified time)
  - per clip it writes (project = folder, created if missing):
      sources.json                      [{clip:"c1",path,dur,w,h,fps,rotation,hash}]  (w/h = as displayed, rotation honoured)
      work/c1.wav                       16 kHz mono
      work/words_c1_fast.json           [{w,s,e,p}] small.en, word start AND end, whole clip
      work/silence_c1.json              energy silence map {floor_db, quiet_db, speech_db, runs:[[s,e],...]} (measured per clip)
      work/sheet_c1.jpg                 contact sheet, 1 frame / 3 s, time-stamped
      transcript.txt                    per clip: [start-end] lines, silences, then words@start-end
  - everything slow is cached by content hash in ~/.reel-room/cache/<hash>/ so a re-run takes seconds
  - running again with more clips appends (c2, c3, ...); the same file keeps its clip id
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

VIDEO_EXT = {'.mov', '.mp4', '.m4v', '.mkv', '.webm', '.avi', '.mts', '.m2ts', '.mpg', '.mpeg'}
FAST_MODEL = 'small.en'
SHEET_EVERY = 3.0      # seconds between contact sheet frames
MIN_SILENCE = 0.25     # report silence runs at least this long


def collect(inputs, newest):
    files = []
    for x in inputs:
        p = Path(x).expanduser()
        if p.is_dir():
            files += [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith('.')]
        elif p.is_file():
            files.append(p)
        else:
            C.fail(f'Not found: {p}', 'Check the path (quote it if it has spaces).')
    files = sorted(set(files), key=lambda f: f.stat().st_mtime, reverse=True)
    if newest:
        files = files[:newest]
        files.sort(key=lambda f: f.stat().st_mtime)   # oldest first = filming order
    else:
        files.sort(key=lambda f: f.name)
    return files


def make_sheet(src, info, dest):
    """contact sheet: 1 frame / 3 s as time-stamped tiles"""
    from PIL import Image, ImageDraw, ImageFont
    portrait = info['h'] >= info['w']
    box = (135, 240) if portrait else (256, 144)
    cols = 12 if portrait else 6
    with tempfile.TemporaryDirectory() as td:
        C.ffmpeg(['-i', src, '-vf', f'fps=1/{SHEET_EVERY:g},scale={box[0]}:{box[1]}:force_original_aspect_ratio=decrease',
                  '-an', '-sn', '-dn', '-q:v', '4', str(Path(td) / 't_%04d.jpg')])
        frames = sorted(Path(td).glob('t_*.jpg'))
        if not frames:
            return None
        try:
            font = ImageFont.load_default(size=13)
        except TypeError:
            font = ImageFont.load_default()
        per_sheet = cols * 10
        paths = []
        for page, start in enumerate(range(0, len(frames), per_sheet)):
            chunk = frames[start:start + per_sheet]
            rows = (len(chunk) + cols - 1) // cols
            sheet = Image.new('RGB', (cols * box[0], rows * box[1]), (12, 12, 15))
            d = ImageDraw.Draw(sheet)
            for i, f in enumerate(chunk):
                im = Image.open(f)
                x, y = (i % cols) * box[0], (i // cols) * box[1]
                sheet.paste(im, (x + (box[0] - im.width) // 2, y + (box[1] - im.height) // 2))
                t = (start + i) * SHEET_EVERY
                label = f'{int(t // 60)}:{int(t % 60):02d}'
                d.rectangle([x, y, x + 38, y + 16], fill=(0, 0, 0))
                d.text((x + 3, y + 1), label, fill=(255, 255, 255), font=font)
            out = dest if page == 0 else dest.with_name(dest.stem + f'_{page + 1}' + dest.suffix)
            sheet.save(out, quality=82)
            paths.append(str(out))
    return paths


def transcribe_fast(wav, model_name, prompt=None):
    import numpy as np
    from splice import read_wav
    a, sr = read_wav(wav)
    audio = (a / 32768.0).astype(np.float32)
    model = C.whisper_model(model_name)
    segs, _ = model.transcribe(audio, word_timestamps=True, condition_on_previous_text=False, beam_size=1, temperature=0.0,
                               language='en', initial_prompt=prompt)
    lines, words = [], []
    for s in segs:
        lines.append({'s': round(s.start, 2), 'e': round(s.end, 2), 'text': s.text.strip()})
        for w in s.words or []:
            words.append({'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3), 'p': round(w.probability, 3)})
    from splice import refine_words, load_env
    words, dropped = refine_words(C.drop_zero_length(words), load_env(wav))
    return lines, words


def silence_map(wav):
    from splice import load_env
    env = load_env(wav)
    q = env.q
    runs, i, n = [], 0, len(q)
    from splice import HOP
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            if (j - i) * HOP >= MIN_SILENCE:
                runs.append([round(i * HOP, 2), round(j * HOP, 2)])
            i = j
        else:
            i += 1
    from splice import BREATH_DB
    return {'floor_db': round(env.floor, 1), 'quiet_db': round(env.floor + BREATH_DB, 1),
            'speech_db': round(env.speech, 1), 'min_run_s': MIN_SILENCE, 'runs': runs}


def fmt_t(t):
    return f'{t:7.2f}'


def write_transcript(proj, sources, per_clip):
    out = []
    for s in sources:
        d = per_clip.get(s['clip'])
        if not d:
            continue
        out.append(f"===== {s['clip']}  {Path(s['path']).name}  ({s['dur']:.1f}s, {s['w']}x{s['h']}, {s['fps']:g} fps)")
        for ln in d['lines']:
            out.append(f"[{fmt_t(ln['s'])}-{fmt_t(ln['e'])}] {ln['text']}")
        runs = d['silence']['runs']
        out.append(f"\n-- silences >= {MIN_SILENCE}s (noise floor {d['silence']['floor_db']} dB) --")
        out.append('  '.join(f'{a:.2f}-{b:.2f}' for a, b in runs) or '(none)')
        out.append('\n-- words@start-end --')
        row = []
        for w in d['words']:
            row.append(f"{w['w']}@{w['s']:.2f}-{w['e']:.2f}")
            if len(row) == 8:
                out.append('  '.join(row)); row = []
        if row:
            out.append('  '.join(row))
        out.append('')
    (Path(proj) / 'transcript.txt').write_text('\n'.join(out), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description='Ingest raw clips: probe, wav, contact sheet, fast transcript, silence map.')
    ap.add_argument('project')
    ap.add_argument('clips', nargs='+', help='video files and/or folders')
    ap.add_argument('--newest', type=int, default=0, help='keep only the N newest clips found')
    ap.add_argument('--model', default=FAST_MODEL)
    ap.add_argument('--no-sheet', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    files = collect(a.clips, a.newest)
    if not files:
        C.fail('No video files found in what you gave me.', f"Pass clip files or a folder with {', '.join(sorted(VIDEO_EXT))} files.", a.json)
    proj = Path(a.project).expanduser()
    (proj / 'work').mkdir(parents=True, exist_ok=True)
    (proj / 'assets').mkdir(exist_ok=True)

    sf = proj / 'sources.json'
    existing = C.read_json(sf) if sf.exists() else []
    if isinstance(existing, dict):
        existing = [{'clip': k, 'path': v} for k, v in existing.items()]
    sources = list(existing)
    prompt = C.names_prompt(proj)
    pk = hashlib.blake2b((prompt or '').encode(), digest_size=4).hexdigest()
    out.log('names hint: ' + (prompt if prompt else 'none') + '. Proper nouns go one per line in ~/.reel-room/names.txt or ' + str(proj / 'names.txt'))
    timings, per_clip, t_all = {}, {}, time.time()
    for f in files:
        t0 = time.time()
        try:
            info = C.probe(f)
        except RuntimeError as e:
            C.fail(str(e), 'Is this a real video file? Try opening it in a player; re-export it if it will not play.', a.json)
        h = C.content_hash(f)
        entry = next((s for s in sources if s.get('hash') == h or Path(s['path']).resolve() == f.resolve()), None)
        if entry is None:
            n = 1 + max([int(s['clip'][1:]) for s in sources if s['clip'][1:].isdigit()] or [0])
            entry = {'clip': f'c{n}'}
            sources.append(entry)
        entry.update({'path': str(f.resolve()), 'dur': info['dur'], 'w': info['w'], 'h': info['h'], 'fps': info['fps'],
                      'rotation': info['rotation'], 'hash': h})
        if not info['has_audio']:
            C.fail(f'{f.name} has no audio track.', 'Reel Room cuts on speech; use a clip recorded with sound.', a.json)
        clip = entry['clip']
        cdir = C.CACHE / h
        cdir.mkdir(parents=True, exist_ok=True)
        out.log(f"[{clip}] {f.name}: {info['w']}x{info['h']} {info['fps']:g} fps {info['dur']:.1f}s rotation {info['rotation']}")
        tm = {}
        # wav
        t1 = time.time()
        wav_c = cdir / 'audio16k.wav'
        if not wav_c.exists():
            C.ffmpeg(['-i', f, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav_c) + '.part.wav'])
            Path(str(wav_c) + '.part.wav').replace(wav_c)
        shutil.copyfile(wav_c, proj / 'work' / f'{clip}.wav')
        tm['wav'] = round(time.time() - t1, 1)
        # silence map
        t1 = time.time()
        sil_c = cdir / 'silence.json'
        if sil_c.exists():
            sil = C.read_json(sil_c)
        else:
            sil = silence_map(wav_c)
            C.write_json(sil_c, sil, indent=None)
        C.write_json(proj / 'work' / f'silence_{clip}.json', sil, indent=None)
        tm['silence'] = round(time.time() - t1, 1)
        # fast transcript
        t1 = time.time()
        tr_c = cdir / f'fast_{a.model}_{pk}_r2.json'
        if tr_c.exists():
            tr = C.read_json(tr_c); tm['transcribe'] = 'cached'
        else:
            out.log(f'[{clip}] transcribing with {a.model} ...')
            lines, words = transcribe_fast(wav_c, a.model, prompt)
            tr = {'lines': lines, 'words': words}
            C.write_json(tr_c, tr, indent=None)
            tm['transcribe'] = round(time.time() - t1, 1)
        C.write_json(proj / 'work' / f'words_{clip}_fast.json', tr['words'], indent=None)
        # contact sheet
        t1 = time.time()
        sheet = None
        if not a.no_sheet:
            sh_c = cdir / 'sheet.jpg'
            if sh_c.exists():
                sheet = [str(proj / 'work' / f'sheet_{clip}.jpg')]
                shutil.copyfile(sh_c, sheet[0])
                for extra in sorted(cdir.glob('sheet_*.jpg')):
                    shutil.copyfile(extra, proj / 'work' / f'sheet_{clip}{extra.name[5:]}')
                tm['sheet'] = 'cached'
            else:
                sheet = make_sheet(f, info, sh_c)
                for p in sheet or []:
                    pp = Path(p)
                    shutil.copyfile(pp, proj / 'work' / (f'sheet_{clip}.jpg' if pp.name == 'sheet.jpg' else f'sheet_{clip}{pp.name[5:]}'))
                sheet = [str(proj / 'work' / f'sheet_{clip}.jpg')] if sheet else None
                tm['sheet'] = round(time.time() - t1, 1)
        per_clip[clip] = {'lines': tr['lines'], 'words': tr['words'], 'silence': sil}
        timings[clip] = {**tm, 'total': round(time.time() - t0, 1)}
        out.log(f"[{clip}] {len(tr['words'])} words, {len(sil['runs'])} silences, noise floor {sil['floor_db']} dB; {timings[clip]}")

    sources.sort(key=lambda s: int(s['clip'][1:]))
    C.write_json(sf, sources)
    # transcript.txt covers every clip, including ones from earlier runs
    for s in sources:
        if s['clip'] not in per_clip:
            wf, sf2 = proj / 'work' / f"words_{s['clip']}_fast.json", proj / 'work' / f"silence_{s['clip']}.json"
            if wf.exists() and sf2.exists():
                cdir = C.CACHE / s.get('hash', '')
                trc = cdir / f'fast_{a.model}_{pk}_r2.json'
                lines = C.read_json(trc)['lines'] if trc.exists() else []
                per_clip[s['clip']] = {'lines': lines, 'words': C.read_json(wf), 'silence': C.read_json(sf2)}
    write_transcript(proj, sources, per_clip)
    out.log(f'wrote {sf} and {proj / "transcript.txt"} in {time.time() - t_all:.1f}s')
    out.result({'ok': True, 'command': 'ingest', 'project': str(proj), 'sources': sources, 'timings': timings,
                'transcript': str(proj / 'transcript.txt'), 'seconds': round(time.time() - t_all, 1)})


if __name__ == '__main__':
    main()
