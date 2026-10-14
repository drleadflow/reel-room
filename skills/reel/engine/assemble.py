"""Assemble the A-roll: cut every EDL segment from the ORIGINAL clip at full resolution, frame-exact.

Usage: assemble.py <project> [--json] [--jobs N] [--crf 14] [--no-verify]
Reads   edl.json, sources.json, project.json (optional `grade.filter` = an ffmpeg filter chain)
Writes  assets/aroll.mp4      1080x1920, 30 fps constant, H.264 + AAC 48 kHz, exactly sum(frames) frames
        segments.json         [{...edl fields, id, frame, frames, src_in, src_out}]  frame = first frame in the cut
        words.json            built by words.py from the FINAL audio + caption_fixes.json (never edited by hand here); --no-words skips it
How it stays exact:
  - frames per segment = round((out-in)*30); video is cropped/zoomed around (cx,cy) from the full-res source, then scaled
  - each segment's audio is resampled to 48 kHz and padded/trimmed to EXACTLY frames*1600 samples, with a 20 ms fade-in
    and a 30 ms fade-out, so every join is click-free and the audio can never drift against the picture
  - segments are joined WITHOUT re-encoding (video) and the audio is encoded to AAC once, at the end
  - rendered segments are cached in work/segs/ by their settings, so re-assembling after a small edit only renders what changed
Drift check (printed and returned): frame count vs plan, worst video timestamp error, audio length vs picture length, and
the audio offset of every segment against the source (cross-correlation).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT_W, OUT_H, FPS = 1080, 1920, C.FPS
SR = 48000
SPF = SR // FPS            # audio samples per video frame (1600)
FADE_IN, FADE_OUT = 0.020, 0.030
ENGINE_VERSION = 'assemble-4'


def crop_box(W, H, zoom, cx, cy):
    """9:16 crop window (even ints) of size base/zoom centred on (cx,cy) given as fractions of the full frame"""
    if W / H > OUT_W / OUT_H:
        bh, bw = H, H * OUT_W / OUT_H
    else:
        bw, bh = W, W * OUT_H / OUT_W
    zoom = max(1.0, float(zoom or 1.0))
    cw, ch = bw / zoom, bh / zoom
    x = min(max(cx * W - cw / 2, 0), W - cw)
    y = min(max(cy * H - ch / 2, 0), H - ch)
    ev = lambda v: int(v) // 2 * 2  # noqa: E731
    return ev(cw), ev(ch), ev(x), ev(y)


def seg_key(src_hash, s, frames, vf_extra, crf):
    blob = json.dumps([ENGINE_VERSION, src_hash, s['in'], frames, s.get('zoom', 1.0), s.get('cx', 0.5), s.get('cy', 0.5),
                       vf_extra, crf], sort_keys=True)
    return hashlib.blake2b(blob.encode(), digest_size=8).hexdigest()


def render_segment(s, frames, src, info, channels, vf_extra, crf, segdir, key):
    v_out, a_out = segdir / f'{key}.h264', segdir / f'{key}.wav'
    if v_out.exists() and a_out.exists():
        return 'cached'
    cw, ch, x, y = crop_box(info['w'], info['h'], s.get('zoom', 1.0), s.get('cx', 0.5), s.get('cy', 0.5))
    vf = f'crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos'
    if vf_extra:
        vf += ',' + vf_extra
    vf += f',fps={FPS},tpad=stop_mode=clone:stop=4,setsar=1,format=yuv420p'
    tmp_v = segdir / f'{key}.part.h264'
    C.ffmpeg(['-ss', f"{s['in']:.4f}", '-i', src, '-an', '-sn', '-dn', '-vf', vf, '-frames:v', frames,
              '-c:v', 'libx264', '-preset', 'medium', '-crf', crf, '-r', FPS, '-g', FPS, '-bf', 0,
              '-x264-params', 'scenecut=0', '-f', 'h264', tmp_v])
    n_samples = frames * SPF
    dur = frames / FPS
    af = (f'aresample={SR},apad=whole_len={n_samples},atrim=end_sample={n_samples},'
          f'afade=t=in:st=0:d={FADE_IN},afade=t=out:st={dur - FADE_OUT:.4f}:d={FADE_OUT}')
    tmp_a = segdir / f'{key}.part.wav'
    C.ffmpeg(['-ss', f"{s['in']:.4f}", '-t', f'{dur + 0.5:.4f}', '-i', src, '-vn', '-sn', '-dn', '-map', '0:a:0',
              '-af', af, '-ac', channels, '-c:a', 'pcm_s16le', tmp_a])
    tmp_a.replace(a_out)
    tmp_v.replace(v_out)
    return 'rendered'


def concat_wavs(paths, dest, channels):
    with wave.open(str(dest), 'wb') as out:
        out.setnchannels(channels); out.setsampwidth(2); out.setframerate(SR)
        for p in paths:
            with wave.open(str(p)) as w:
                out.writeframes(w.readframes(w.getnframes()))


def xcorr_lag_ms(a, b, sr):
    """lag of a relative to b in ms (positive = a is later). Both mono float arrays."""
    import numpy as np
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    A, B = np.fft.rfft(a, n), np.fft.rfft(b, n)
    c = np.fft.irfft(A * np.conj(B), n)
    k = int(np.argmax(np.concatenate([c[-(len(b) - 1):], c[:len(a)]]))) - (len(b) - 1)
    return k / sr * 1000


def verify(proj, segments, out_path, out):
    import numpy as np
    from splice import read_wav
    planned = sum(s['frames'] for s in segments)
    r = C.run([C.ffprobe_bin(), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time',
               '-of', 'csv=p=0', out_path])
    pts = sorted(float(x) for x in r.stdout.split() if x.strip())
    n = len(pts)
    err = max((abs(p - i / FPS) for i, p in enumerate(pts)), default=0.0)
    last = segments[-1]
    last_err = abs(pts[last['frame']] - last['frame'] / FPS) if last['frame'] < n else float('inf')
    # audio length (decode to 48 kHz mono and count samples)
    import subprocess
    raw = subprocess.run([C.ffmpeg_bin(), '-v', 'error', '-i', str(out_path), '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True).stdout
    a_samples = len(raw) // 2
    a_dur, v_dur = a_samples / SR, planned / FPS
    # per-segment audio offset against the source
    lags, worst = [], 0.0
    srcs = C.source_info(proj)
    cache16 = {}
    mono = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    for s in segments:
        wavp = Path(proj) / 'work' / f"{s['clip']}.wav"
        if not wavp.exists():
            continue
        if s['clip'] not in cache16:
            cache16[s['clip']] = read_wav(wavp)[0]
        src = cache16[s['clip']]
        ln = min(s['frames'] / FPS - 0.1, 1.2)
        if ln < 0.25:
            continue
        a0 = int((s['frame'] / FPS + 0.05) * SR)
        seg_a = mono[a0:a0 + int(ln * SR)][::3]            # 48k -> 16k (box decimation is good enough for lag)
        s0 = max(0, int((s['src_in'] + 0.05 - 0.15) * 16000))
        src_a = src[s0:s0 + int((ln + 0.3) * 16000)]
        if len(seg_a) < 2000 or len(src_a) < len(seg_a) or seg_a.std() < 1e-3:
            continue
        lag = xcorr_lag_ms(src_a, seg_a, 16000) - 150.0     # position of the segment inside the padded source window, minus the pad
        lags.append((s['id'], round(lag, 1)))
        worst = max(worst, abs(lag))
    res = {'planned_frames': planned, 'video_packets': n, 'frame_count_ok': n == planned,
           'max_video_pts_error_ms': round(err * 1000, 3), 'last_segment_first_frame_error_ms': round(last_err * 1000, 3),
           'audio_seconds': round(a_dur, 4), 'video_seconds': round(v_dur, 4),
           'audio_minus_video_ms': round((a_dur - v_dur) * 1000, 2), 'worst_segment_audio_offset_ms': round(worst, 1),
           'segment_audio_offsets_ms': dict(lags)}
    res['drift_free'] = (res['frame_count_ok'] and err < 0.002 and last_err < 0.002 and abs(a_dur - v_dur) < 0.025 and worst < 25)
    return res


def main():
    ap = argparse.ArgumentParser(description='Assemble assets/aroll.mp4 from edl.json (frame-exact).')
    ap.add_argument('project')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--jobs', type=int, default=0, help='parallel segment renders (default: auto)')
    ap.add_argument('--crf', type=int, default=14)
    ap.add_argument('--no-verify', action='store_true')
    ap.add_argument('--no-words', action='store_true', help='do not (re)build words.json from the final audio')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    proj = C.need_project(a.project, ['edl.json', 'sources.json'], a.json)
    t_all = time.time()
    edl = C.read_json(proj / 'edl.json')
    if not edl:
        C.fail('edl.json is empty.', 'Add at least one segment: {id, clip, in, out, mode, zoom, cx, cy, line}.', a.json)
    srcs = C.source_info(proj)
    for s in edl:
        if s['clip'] not in srcs:
            C.fail(f"Segment '{s['id']}' uses clip {s['clip']} which is not in sources.json.", 'Run ingest.py for that clip.', a.json)
        if s['out'] <= s['in']:
            C.fail(f"Segment '{s['id']}' ends before it starts ({s['in']} to {s['out']}).", 'Fix in/out in edl.json.', a.json)
    ids = [s['id'] for s in edl]
    if len(set(ids)) != len(ids):
        C.fail('Two segments share the same id in edl.json.', 'Give every segment a unique id.', a.json)
    pj = C.read_json(proj / 'project.json', default={}) if (proj / 'project.json').exists() else {}
    vf_extra = (pj.get('grade') or {}).get('filter', '') or ''
    segments = C.layout(edl)
    info, chans = {}, {}
    for c, si in srcs.items():
        p = Path(si['path'])
        if not p.exists():
            C.fail(f'Source clip {p} is missing.', 'Move it back or fix the path in sources.json.', a.json)
        if 'w' not in si or not si.get('hash'):
            si.update({k: v for k, v in C.probe(p).items() if k in ('w', 'h')}); si['hash'] = C.content_hash(p)
        info[c] = si
        j = C.ffprobe_json(p)
        ach = next((int(x.get('channels', 1)) for x in j['streams'] if x['codec_type'] == 'audio'), 0)
        if not ach:
            C.fail(f'{p.name} has no audio track.', 'Use a clip recorded with sound.', a.json)
        chans[c] = min(ach, 2)
    ch_out = max(chans[s['clip']] for s in segments)
    segdir = proj / 'work' / 'segs'
    segdir.mkdir(parents=True, exist_ok=True)
    (proj / 'assets').mkdir(exist_ok=True)
    for s in segments:
        s['_key'] = seg_key(info[s['clip']]['hash'], s, s['frames'], vf_extra, a.crf)
    jobs = a.jobs or max(1, min(4, (os.cpu_count() or 4) // 3))
    jobs = C._RL.pool_workers(jobs, per_worker=2)    # engine-wide CPU budget (rrlimits): fewer jobs, shared threads
    C._RL.share(jobs)
    out.log(f"assembling {len(segments)} segments, {sum(s['frames'] for s in segments)} frames "
            f"({sum(s['frames'] for s in segments) / FPS:.1f} s), {jobs} parallel jobs" + (f", grade: {vf_extra}" if vf_extra else ''))

    done = [0]

    def work(s):
        r = render_segment(s, s['frames'], info[s['clip']]['path'], info[s['clip']], ch_out, vf_extra, a.crf, segdir, s['_key'])
        done[0] += 1
        out.log(f"  [{done[0]}/{len(segments)}] {s['id']}: {s['frames']} frames ({r})")
        return r

    t0 = time.time()
    try:
        with ThreadPoolExecutor(jobs) as ex:
            results = list(ex.map(work, segments))
    except RuntimeError as e:
        C.fail(str(e), 'Check the segment times in edl.json are inside the clip, then run assemble again.', a.json)
    t_render = time.time() - t0

    # join: raw H.264 segments are concatenated byte-for-byte and stamped at exactly 30 fps, so frame N is always at N/30
    full_h264 = proj / 'work' / 'aroll.h264'
    with open(full_h264, 'wb') as fo:
        for s in segments:
            with open(segdir / f"{s['_key']}.h264", 'rb') as fi:
                shutil.copyfileobj(fi, fo)
    full_wav = proj / 'work' / 'aroll.wav'
    concat_wavs([segdir / f"{s['_key']}.wav" for s in segments], full_wav, ch_out)
    dest = proj / 'assets' / 'aroll.mp4'
    tmp = proj / 'assets' / 'aroll.part.mp4'
    C.ffmpeg(['-framerate', FPS, '-f', 'h264', '-i', full_h264, '-i', full_wav, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
              '-c:a', 'aac', '-b:a', '192k', '-ar', SR, '-movflags', '+faststart', tmp])
    tmp.replace(dest)
    full_h264.unlink()
    # iPhone HLG/PQ tags would switch HyperFrames to HDR and drop alpha on every cut-out layer: retag bt709 (lossless)
    try:
        import hdr
        fixed = hdr.fix_file(str(dest))
        if fixed["action"] != "none":
            out.log(f"hdr: aroll.mp4 {fixed['action']} (was {fixed['before']['trc']})")
    except Exception as e:  # never lose the cut over a tag; render prep (hdr.fix_project) retries
        out.log(f"WARNING: could not retag aroll.mp4 as SDR ({e}); render prep will retry")

    # clean stale cache files
    keep = {s['_key'] for s in segments}
    for f in segdir.iterdir():
        if f.suffix in ('.mp4', '.wav', '.h264', '.txt') and f.stem.split('.')[0] not in keep:
            f.unlink()
    segs_out = [{k: v for k, v in s.items() if not k.startswith('_')} for s in segments]
    C.write_json(proj / 'segments.json', segs_out)
    # the seek + fps step can repeat a frame (first frame of a cut, or every third frame): measure and fix (aroll_fix.py)
    afix = None
    if pj.get('aroll_fix', 'auto') != 'off':
        import aroll_fix
        afix = aroll_fix.auto(proj, out.log, a.crf)

    # captions words (cut time): transcribe the FINAL audio + re-apply caption_fixes.json. words.json is never edited here.
    nwords = None
    if not a.no_words:
        try:
            import words as W
            nwords = len(W.build(proj, out))
        except SystemExit:
            raise
        except Exception as e:   # keep the cut; the old words.json (if any) stays untouched
            out.log(f"WARNING: could not build words.json ({e}). Run: words.py {proj} build")

    res = {'ok': True, 'command': 'assemble', 'output': str(dest), 'segments': len(segs_out),
           'frames': sum(s['frames'] for s in segs_out), 'seconds_of_video': round(sum(s['frames'] for s in segs_out) / FPS, 2),
           'rendered': results.count('rendered'), 'cached': results.count('cached'), 'words': nwords,
           'render_seconds': round(t_render, 1), 'aroll_fix': afix}
    if not a.no_verify:
        v = verify(proj, segs_out, dest, out)
        res['drift'] = v
        out.log(f"drift check: frames {v['video_packets']}/{v['planned_frames']}, worst video timestamp error "
                f"{v['max_video_pts_error_ms']} ms, last segment first-frame error {v['last_segment_first_frame_error_ms']} ms, "
                f"audio minus video {v['audio_minus_video_ms']} ms, worst segment audio offset {v['worst_segment_audio_offset_ms']} ms "
                f"-> {'NO DRIFT' if v['drift_free'] else 'DRIFT, investigate'}")
    res['total_seconds'] = round(time.time() - t_all, 1)
    out.log(f"wrote {dest} ({res['seconds_of_video']} s), segments.json{', words.json (' + str(nwords) + ' words)' if nwords is not None else ''} in {res['total_seconds']}s")
    out.result(res)


if __name__ == '__main__':
    main()
