"""Storyboard approval hash, computed exactly as the Room page does (djb2 over JSON.stringify(beats), UTF-16 code units, base 36).

Usage: hash.py <project> [--beats FILE] [--write] [--json]
  default beats source: <project>/work/storyboard.json ({"beats":[...]}); falls back to room-sim/storyboard/current.json
  --beats FILE   use another file ({"beats":[...]} or a bare list)
  --write        write <project>/room-sim/storyboard/approval.json = {"ok":true,"note":"approved (simulated)","for":"<hash>"}
                 (only for the offline room simulation; the real Room writes its own approval)
Compare the printed value with storyboard/approval.for from the Room: equal means the user approved these beats.
Numbers are written the way JavaScript does (5.0 -> 5), and key order is kept, so save beats with the same key order you sent
(t,line,clip,layout,insert,flag).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def js_num(x):
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int):
        return str(x)
    if math.isnan(x) or math.isinf(x):
        return 'null'
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def js_stringify(v):
    """JSON.stringify(v) with no spaces, JS number formatting, key order preserved"""
    if v is None:
        return 'null'
    if isinstance(v, (bool, int, float)):
        return js_num(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return '[' + ','.join('null' if x is None else js_stringify(x) for x in v) + ']'
    if isinstance(v, dict):
        return '{' + ','.join(json.dumps(str(k), ensure_ascii=False) + ':' + js_stringify(x) for k, x in sorted(v.items())) + '}'
    return 'null'


def hash_beats(beats):
    u = js_stringify(beats).encode('utf-16-le')
    x = 5381
    for i in range(0, len(u), 2):
        x = ((x << 5) + x + (u[i] | (u[i + 1] << 8))) & 0xFFFFFFFF
    d = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while x:
        x, r = divmod(x, 36)
        out = d[r] + out
    return out or '0'


def main():
    ap = argparse.ArgumentParser(description='Storyboard approval hash (same as the Room).')
    ap.add_argument('project')
    ap.add_argument('--beats')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    out = C.Out(a.json)
    proj = C.need_project(a.project, [], a.json)
    cands = [Path(a.beats).expanduser()] if a.beats else [proj / 'work' / 'storyboard.json', proj / 'room-sim' / 'storyboard' / 'current.json']
    src = next((p for p in cands if p.exists()), None)
    if src is None:
        C.fail('No storyboard found.', 'Save the beats you sent to the Room as work/storyboard.json ({"beats":[...]}), or pass --beats FILE.', a.json)
    data = C.read_json(src)
    beats = data['beats'] if isinstance(data, dict) else data
    h = hash_beats(beats)
    out.log(h)
    if a.write:
        dest = proj / 'room-sim' / 'storyboard' / 'approval.json'
        C.write_json(dest, {'ok': True, 'note': 'approved (simulated)', 'for': h}, indent=None)
        out.log(f'wrote {dest}')
    out.result({'ok': True, 'command': 'hash', 'hash': h, 'beats': len(beats), 'source': str(src)})


if __name__ == '__main__':
    main()
