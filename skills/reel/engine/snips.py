"""Apply review snips and frame nudges from the Room to the edit list (edl.json).

Usage: snips.py <project> apply            apply every pending snip in work/snips.json
       snips.py <project> undo <id> [id..]   remove snip(s) and rebuild the EDL from the saved original
       snips.py <project> list             show snips and what was applied
       snips.py <project> reset            go back to the original EDL (all snips become pending again)
       add --json to any command for machine-readable output
After apply/undo: run assemble.py, then splice.py joins, then re-render.

work/snips.json (Claude exports it from the Room db). A list, {"snips":[...]} or {id: doc}. Each doc is one of
  range  {id, t0, t1, text?, status:"pending", round?}         cut-time seconds (the cut the reviewer watched)
  words  {id, words:[{start,end}, ...]}  or  {id, word_range:[i0,i1]} (indexes into words.json)   -> one range
  nudge  {id, kind:"nudge", seg:"n1b", edge:"in"|"out", delta_frames:-2}   moves that edge by N/30 s (+ = later)
Rules
  - cut time is mapped to source time with segments.json (the cut the reviewer saw); segments that are split get
    ids  <id>, <id>~1, <id>~2 ...; pieces shorter than 3 frames are dropped
  - the two new edges are re-snapped like `splice.py snap` does: the left piece ends in the silence after its last kept
    word, the right piece starts in the silence before its first kept word (word timings from the precise/fast words)
  - nudged edges get lock_in / lock_out so a later `splice.py snap` does not undo them
  - everything else in the EDL stays byte-identical; `line` of split pieces is rebuilt from the words they still contain
  - the right piece of a split carries "needs_layout_change": true (a jump cut should land on a layout change)
  - the original EDL is kept once as work/edl.original.json; every applied operation is logged in work/snips_log.json
    (cuts are stored as SOURCE ranges, so undoing an old snip never mis-maps later ones). Hand edits to edl.json after the
    first apply are not replayed by `undo`, except Room look changes made with rounds.py (work/beat_looks.json), which are.
"""
from __future__ import annotations

import argparse
import copy
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MIN_PIECE = 0.1    # seconds (3 frames)


# ------------------------------------------------------------------------------------------- reading snips
def load_snips(path):
    raw = C.read_json(path)
    if isinstance(raw, dict) and 'snips' in raw:
        raw = raw['snips']
    if isinstance(raw, dict):
        raw = [{'id': k, **v} for k, v in raw.items()]
    out = []
    for d in raw:
        d = dict(d)
        d.setdefault('status', 'pending')
        if d.get('kind') == 'nudge' or ('seg' in d and 'edge' in d):
            d['kind'] = 'nudge'
        elif 'words' in d or 'word_range' in d:
            d['kind'] = 'words'
        else:
            d['kind'] = 'range'
        out.append(d)
    return out


def snip_range(d, words_json):
    """cut-time (t0,t1) of a range / words snip"""
    if d['kind'] == 'range':
        return float(d['t0']), float(d['t1'])
    if 'word_range' in d:
        i0, i1 = d['word_range']
        ws = words_json[i0:i1 + 1]
    else:
        ws = d['words']
    ws = [w for w in ws if 'start' in w]
    if not ws:
        raise ValueError(f"snip {d.get('id')}: no usable words")
    return min(float(w['start']) for w in ws), max(float(w['end']) for w in ws)


# ------------------------------------------------------------------------------------------- operations
def resolve(d, layout_segs, words_json):
    """snip doc -> list of ops (cuts as source ranges per segment, or a nudge)"""
    if d['kind'] == 'nudge':
        if d['seg'] not in {s['id'] for s in layout_segs}:
            raise ValueError(f"snip {d.get('id')}: segment '{d['seg']}' is not in the current cut")
        if d['edge'] not in ('in', 'out'):
            raise ValueError(f"snip {d.get('id')}: edge must be 'in' or 'out'")
        return [{'type': 'nudge', 'snip': d['id'], 'seg': d['seg'], 'edge': d['edge'], 'delta_frames': int(d['delta_frames'])}]
    t0, t1 = snip_range(d, words_json)
    if t1 <= t0:
        raise ValueError(f"snip {d.get('id')}: end is not after start ({t0} to {t1})")
    ops = []
    for s in layout_segs:
        f0, f1 = s['frame'] / C.FPS, (s['frame'] + s['frames']) / C.FPS
        x, y = max(t0, f0), min(t1, f1)
        if y - x > 1e-6:
            ops.append({'type': 'cut', 'snip': d['id'], 'seg': s['id'], 'clip': s['clip'],
                        't0': round(s['src_in'] + (x - f0), 3), 't1': round(s['src_in'] + (y - f0), 3)})
    if not ops:
        raise ValueError(f"snip {d.get('id')}: {t0:.2f}-{t1:.2f} s is outside the cut")
    return ops


def base_id(i):
    return i.split('~')[0]


def apply_cut(edl, op):
    out, hit = [], False
    for s in edl:
        a, b = s['in'], s['out']
        if s['clip'] != op['clip'] or base_id(s['id']) != base_id(op['seg']) or op['t1'] <= a or op['t0'] >= b:
            out.append(s); continue
        hit = True
        pieces = []
        if op['t0'] - a >= MIN_PIECE:
            p = copy.deepcopy(s); p['out'] = round(op['t0'], 3); p['_new_out'] = op['t0']; p.pop('lock_out', None)
            pieces.append(p)
        if b - op['t1'] >= MIN_PIECE:
            p = copy.deepcopy(s); p['in'] = round(op['t1'], 3); p['_new_in'] = op['t1']; p.pop('lock_in', None)
            if pieces:
                p['needs_layout_change'] = True
            pieces.append(p)
        for n, p in enumerate(pieces):
            nid = s['id'] if n == 0 else f"{base_id(s['id'])}~{_next_suffix(edl, out, s['id'])}"
            p['id'] = nid
            if n == 0 and len(pieces) == 1:
                # single surviving piece: keep the lock on the edge that did not change
                if '_new_out' in p and 'lock_in' in s: p['lock_in'] = s['lock_in']
                if '_new_in' in p and 'lock_out' in s: p['lock_out'] = s['lock_out']
            out.append(p)
    if not hit:
        raise ValueError(f"cut {op['t0']}-{op['t1']} on '{op['seg']}' matches nothing in the EDL (already applied?)")
    return out


def _next_suffix(edl, out, sid):
    used = {s['id'] for s in edl} | {s['id'] for s in out}
    n = 1
    while f"{base_id(sid)}~{n}" in used:
        n += 1
    return n


def apply_nudge(edl, op):
    cand = [s for s in edl if base_id(s['id']) == base_id(op['seg'])]
    if not cand:
        raise ValueError(f"nudge: segment '{op['seg']}' not in the EDL")
    s = cand[0] if op['edge'] == 'in' else cand[-1]
    d = op['delta_frames'] / C.FPS
    if op['edge'] == 'in':
        s['in'] = round(max(0.0, s['in'] + d), 3); s['lock_in'] = True
    else:
        s['out'] = round(s['out'] + d, 3); s['lock_out'] = True
    if s['out'] - s['in'] < MIN_PIECE:
        raise ValueError(f"nudge on '{s['id']}' would leave less than 3 frames")
    return edl


def snap_new_edges(proj, edl, notes):
    """re-snap edges created by cuts to the silence next to the nearest kept word; rebuild the line of split pieces"""
    import splice
    envs, words = {}, {}
    for s in edl:
        if not ('_new_in' in s or '_new_out' in s):
            continue
        c = s['clip']
        if c not in envs:
            wav = Path(proj) / 'work' / f'{c}.wav'
            envs[c] = splice.load_env(wav) if wav.exists() else None
            words[c] = C.best_words(proj, c)
        env, ws = envs[c], words[c]
        if '_new_out' in s:
            t = s.pop('_new_out')
            kept = [w for w in ws if w['e'] <= t + 0.03 and w['e'] > s['in']]
            anchor = kept[-1]['e'] if kept else t
            if env is not None:
                new, note = splice.snap_out(env, anchor, hi=t + 0.02)
                s['out'] = round(max(s['in'] + MIN_PIECE, new), 3)
                if not note.startswith('ok'): notes.append(f"{s['id']} out: {note}")
        if '_new_in' in s:
            t = s.pop('_new_in')
            kept = [w for w in ws if w['s'] >= t - 0.03 and w['s'] < s['out']]
            anchor = kept[0]['s'] if kept else t
            if env is not None:
                new, note = splice.snap_in(env, anchor, lo=t - 0.02)
                s['in'] = round(min(s['out'] - MIN_PIECE, new), 3)
                if not note.startswith('ok'): notes.append(f"{s['id']} in: {note}")
        inside = [w['w'] for w in ws if s['in'] <= (w['s'] + w['e']) / 2 < s['out']]
        if inside:
            s['line'] = ' '.join(inside)
    # neighbours made from one segment must not overlap after snapping
    for p, q in zip(edl, edl[1:]):
        if base_id(p['id']) == base_id(q['id']) and p['clip'] == q['clip'] and p['out'] > q['in']:
            mid = round((p['out'] + q['in']) / 2, 3)
            p['out'] = q['in'] = mid
            notes.append(f"{p['id']} | {q['id']}: removed range was too short to snap cleanly, joined at {mid}")
    return edl


def apply_ops(proj, edl, ops, notes):
    for op in ops:
        edl = apply_cut(edl, op) if op['type'] == 'cut' else apply_nudge(edl, op)
        edl = snap_new_edges(proj, edl, notes)
    return edl


# ------------------------------------------------------------------------------------------- commands
def paths(proj):
    w = Path(proj) / 'work'
    return {'snips': w / 'snips.json', 'log': w / 'snips_log.json', 'orig': w / 'edl.original.json',
            'text': w / 'snips.log.txt', 'edl': Path(proj) / 'edl.json'}


def current_layout(proj, edl):
    sj = Path(proj) / 'segments.json'
    if sj.exists():
        segs = C.read_json(sj)
        if [s['id'] for s in segs] == [s['id'] for s in edl]:
            return segs, 'segments.json'
    return C.layout(edl), 'edl.json (segments.json missing or older than edl.json)'


def save_snips(p, snips):
    C.write_json(p['snips'], {'snips': snips})


def cmd_apply(proj, out):
    p = paths(proj)
    if not p['snips'].exists():
        C.fail('work/snips.json not found: there is nothing to apply.',
               'Export the Room snips to work/snips.json first (Claude reads snips/* from the Room db and writes it).', out.json)
    snips = load_snips(p['snips'])
    log = C.read_json(p['log']) if p['log'].exists() else {'round': 0, 'ops': [], 'applied': []}
    pending = [d for d in snips if d['status'] == 'pending' and d['id'] not in log['applied']]
    if not pending:
        out.log('No pending snips.')
        return out.result({'ok': True, 'command': 'apply', 'applied': [], 'message': 'no pending snips'})
    edl = C.read_json(p['edl'])
    if not p['orig'].exists():
        shutil.copyfile(p['edl'], p['orig'])
    segs, src = current_layout(proj, edl)
    wf = Path(proj) / 'words.json'
    wj = C.read_json(wf) if wf.exists() else []
    ops, errors = [], []
    for d in pending:
        try:
            ops += resolve(d, segs, wj)
        except (ValueError, KeyError, TypeError) as e:
            errors.append({'snip': d.get('id'), 'error': str(e)})
            d['status'] = 'error'; d['error'] = str(e)
    ops.sort(key=lambda o: 0 if o['type'] == 'cut' else 1)    # cuts first, then nudges on the resulting pieces
    notes = []
    before = len(edl)
    shutil.copyfile(p['edl'], Path(proj) / 'work' / f"edl.r{log['round']}.json")
    try:
        new_edl = apply_ops(proj, edl, ops, notes)
    except ValueError as e:
        C.fail(str(e), 'Nothing was changed. Check work/snips.json (is it already applied? run `snips.py list`).', out.json)
    log['round'] += 1
    for o in ops:
        o['round'] = log['round']
    log['ops'] += ops
    ok_ids = sorted({o['snip'] for o in ops})
    log['applied'] += ok_ids
    for d in snips:
        if d['id'] in ok_ids:
            d['status'] = 'applied'; d['applied_round'] = log['round']
    C.write_json(p['edl'], new_edl)
    C.write_json(p['log'], log)
    save_snips(p, snips)
    with open(p['text'], 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} round {log['round']}: applied {ok_ids}\n")
        for o in ops:
            f.write(f"  {o}\n")
        for n in notes:
            f.write(f"  note: {n}\n")
    out.log(f"applied {len(ok_ids)} snip(s) from {src}: EDL {before} -> {len(new_edl)} segments")
    for o in ops:
        out.log('  ' + (f"cut {o['seg']} source {o['t0']}-{o['t1']}" if o['type'] == 'cut'
                        else f"nudge {o['seg']} {o['edge']} {o['delta_frames']:+d} frames"))
    for n in notes:
        out.log('  note: ' + n)
    for e in errors:
        out.log(f"  could not apply {e['snip']}: {e['error']}")
    out.log('next: run assemble.py, then splice.py joins')
    out.result({'ok': True, 'command': 'apply', 'round': log['round'], 'applied': ok_ids, 'errors': errors, 'notes': notes,
                'segments_before': before, 'segments_after': len(new_edl), 'ops': ops})


def cmd_undo(proj, ids, out, reset=False):
    p = paths(proj)
    if not p['orig'].exists() or not p['log'].exists():
        C.fail('Nothing to undo: no snips have been applied yet.', 'Run `snips.py <project> apply` first.', out.json)
    log = C.read_json(p['log'])
    snips = load_snips(p['snips']) if p['snips'].exists() else []
    drop = set(log['applied']) if reset else set(ids)
    unknown = [i for i in drop if i not in log['applied']]
    if unknown and not reset:
        C.fail(f"Not applied: {', '.join(unknown)}.", 'Run `snips.py <project> list` to see applied snips.', out.json)
    ops = [o for o in log['ops'] if o['snip'] not in drop]
    edl = C.read_json(p['orig'])
    notes = []
    try:
        edl = apply_ops(proj, edl, ops, notes)
    except ValueError as e:
        C.fail(f'Could not rebuild the EDL after removing those snips: {e}',
               'Use `snips.py <project> reset`, then apply the snips you still want.', out.json)
    try:   # Room look changes (rounds.py: go-back, motion levels) live on the EDL; put them back after the rebuild
        import rounds as RD
        edl = RD.reapply_looks(proj, edl, notes)
    except ImportError:
        pass
    log['ops'] = ops
    log['applied'] = [i for i in log['applied'] if i not in drop]
    for d in snips:
        if d['id'] in drop:
            d['status'] = 'pending' if reset else 'removed'
            d.pop('applied_round', None)
    C.write_json(p['edl'], edl)
    C.write_json(p['log'], log)
    if snips:
        save_snips(p, snips)
    with open(p['text'], 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {'reset' if reset else 'undo'} {sorted(drop)}\n")
    out.log(f"{'reset to the original EDL' if reset else 'undid ' + ', '.join(sorted(drop))}: {len(edl)} segments. Next: assemble.py")
    out.result({'ok': True, 'command': 'reset' if reset else 'undo', 'removed': sorted(drop), 'segments': len(edl), 'notes': notes})


def cmd_list(proj, out):
    p = paths(proj)
    snips = load_snips(p['snips']) if p['snips'].exists() else []
    log = C.read_json(p['log']) if p['log'].exists() else {'round': 0, 'applied': []}
    for d in snips:
        what = (f"nudge {d['seg']} {d['edge']} {d['delta_frames']:+d}f" if d['kind'] == 'nudge'
                else f"cut {d.get('t0', '')}-{d.get('t1', '')} {d.get('text', '')}".strip())
        out.log(f"{d['id']:12} {d['status']:8} {what}")
    out.log(f"{len(snips)} snips, {len(log['applied'])} applied, round {log['round']}")
    out.result({'ok': True, 'command': 'list', 'snips': snips, 'applied': log['applied'], 'round': log['round']})


def main():
    ap = argparse.ArgumentParser(description='Apply Room snips and nudges to edl.json.')
    ap.add_argument('project')
    ap.add_argument('cmd', choices=['apply', 'undo', 'list', 'reset'])
    ap.add_argument('ids', nargs='*', help='undo: snip ids')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    C.reexec_in_venv()
    out = C.Out(a.json)
    proj = C.need_project(a.project, ['edl.json'], a.json)
    try:
        if a.cmd == 'apply':
            cmd_apply(proj, out)
        elif a.cmd == 'undo':
            if not a.ids:
                C.fail('Say which snip to undo.', 'Example: snips.py <project> undo s3', a.json)
            cmd_undo(proj, a.ids, out)
        elif a.cmd == 'reset':
            cmd_undo(proj, [], out, reset=True)
        else:
            cmd_list(proj, out)
    except (FileNotFoundError, KeyError, ValueError) as e:
        C.fail(f'{type(e).__name__}: {e}', 'Check work/snips.json matches the format in the snips.py header.', a.json)


if __name__ == '__main__':
    main()
