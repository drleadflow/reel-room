"""Per-beat go-back and motion levels: archive every round's build state per beat, bring one beat back from an older
round, drop one beat a motion level, and apply the Room's motion docs (motion/choice, motion/beats, beat_changes).

Usage: rounds.py <project> snapshot [--round N]       archive the current build as round N (default: last + 1)
       rounds.py <project> list                       rounds and which beats changed between them
       rounds.py <project> index [--out FILE]         the Room doc rounds/index (JSON on stdout or to FILE)
       rounds.py <project> use <seg> <round> [--timing]   bring back round N's version of one beat
       rounds.py <project> simpler <seg>              drop one beat one motion level (showreel > polished > simple)
       rounds.py <project> level <seg> <simple|polished|showreel|reel>   set one beat's level ("reel" = follow the reel)
       rounds.py <project> reel-level <simple|polished|showreel>        project.json motion.level
       rounds.py <project> beatmap                    storyboard beat index -> segment ids (work/beat_map.json)
       rounds.py <project> apply <file.json>          apply exported Room docs (shape below)
       rounds.py <project> diff <a> <b>               beats that differ between two rounds
       add --json to any command for one machine-readable result

What a round archive holds (P/rounds/r<N>/): edl.json, project.json, segments.json, words.json, work/storyboard.json
(when present), meta.json, and beats.json: one entry per segment with its LOOK (every edl key except id and timing:
mode, zoom, cx, cy, top, motion, ...), its TIMING (clip, in, out, line, lock_in, lock_out), its cut-time window, the
project.json "beats" and "overlays" rows that sit inside that window, the effective motion level, and every file those
reference (copied once into P/rounds/blobs/<hash><ext>, so a later regenerated asset never erases an old round).

`use` restores the LOOK by default (what the user calls "the version of this beat"): graphics, layout, zoom, motion.
--timing also restores the take and edges (then assemble must re-run). Rows that span several beats are left alone and
reported. Shifted rows keep their offset inside the beat. A restored file that changed since is written to
assets/rounds/r<N>/ and the reference is pointed there (current files are never overwritten).

Every look change is also recorded in work/beat_looks.json; `snips.py undo` re-applies it after rebuilding the EDL.

apply file (Claude exports it from the Room db, any key optional):
  {"motion_choice": {"level", "at"},
   "motion_beats": {"levels": {"<beatIndex>": "simple|polished|showreel"}, "for": "<storyboard hash>", "at"},
   "beat_changes": [{"id", "kind": "use_round"|"simpler"|"level", "seg", "from_round"?, "level"?, "status": "pending"}]}
-> results per change id, the segments that changed, and what to rebuild ("render" only, or "assemble" when timing moved).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

LEVELS = ["simple", "polished", "showreel"]
TIMING_KEYS = ("clip", "in", "out", "line", "lock_in", "lock_out")
SKIP_KEYS = ("id", "src_in", "src_out", "frame", "frames")
SHOW_MOVES = ["whip", "zoom", "push", "drop", "flash", "smash"]
MEDIA_EXT = {".mp4", ".mov", ".webm", ".m4v", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".wav", ".mp3", ".m4a"}
MAX_BLOB = 200 * 1024 * 1024
EPS = 0.05


# ------------------------------------------------------------------------------------------- small helpers
def base_id(sid):
    return str(sid).split("~")[0]


def sig(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def rdir(proj):
    return Path(proj) / "rounds"


def load(proj, name, default=None):
    p = Path(proj) / name
    return C.read_json(p) if p.exists() else copy.deepcopy(default)


def edl_of(proj):
    return C.read_json(Path(proj) / "edl.json")


def windows(proj, edl):
    """seg id -> (t0, t1) in cut seconds (segments.json when it matches the EDL, else computed from the EDL)"""
    segs = load(proj, "segments.json", [])
    if [s["id"] for s in segs] != [s["id"] for s in edl]:
        segs = C.layout(edl)
    return {s["id"]: (s["frame"] / C.FPS, (s["frame"] + s["frames"]) / C.FPS) for s in segs}


def reel_level(pj):
    m = (pj or {}).get("motion")
    lvl = m.get("level") if isinstance(m, dict) else None
    return lvl if lvl in LEVELS else "polished"


def seg_level(seg, pj):
    m = seg.get("motion") if isinstance(seg.get("motion"), dict) else {}
    return m.get("level") if m.get("level") in LEVELS else reel_level(pj)


def find_seg(edl, sid):
    for s in edl:
        if s["id"] == sid:
            return s
    return next((s for s in edl if base_id(s["id"]) == base_id(sid)), None)


# ------------------------------------------------------------------------------------------- what belongs to a beat
def row_window(row, start_key):
    a, b = row.get(start_key), row.get("until")
    return (float(a) if isinstance(a, (int, float)) else None, float(b) if isinstance(b, (int, float)) else None)


def attached(rows, sid, win, start_key):
    """project.json rows that belong to segment sid: (inside, spanning)"""
    inside, span = [], []
    t0, t1 = win
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            continue
        src = r.get("at_src") if isinstance(r.get("at_src"), dict) else {}
        rs = r.get("seg") or src.get("seg")
        if rs:
            if rs == sid:
                inside.append(i)
            continue
        a, b = row_window(r, start_key)
        if a is None or not (t0 - EPS <= a < t1 - EPS):
            continue
        (inside if b is None or b <= t1 + EPS else span).append(i)
    return inside, span


def file_refs(obj, proj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for v in obj.values():
            file_refs(v, proj, out)
    elif isinstance(obj, list):
        for v in obj:
            file_refs(v, proj, out)
    elif isinstance(obj, str) and Path(obj).suffix.lower() in MEDIA_EXT and "/" in obj:
        if (Path(proj) / obj).is_file():
            out.add(obj)
    return out


def file_hash(path):
    h = hashlib.blake2b(digest_size=8)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_file(proj, rel):
    src = Path(proj) / rel
    if src.stat().st_size > MAX_BLOB:
        return None
    name = file_hash(src) + src.suffix.lower()
    dst = rdir(proj) / "blobs" / name
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return name


def beat_state(proj, seg, win, pj):
    look = {k: v for k, v in seg.items() if k not in TIMING_KEYS and k not in SKIP_KEYS}
    timing = {k: seg[k] for k in TIMING_KEYS if k in seg}
    bi, bs = attached(pj.get("beats"), seg["id"], win, "at")
    oi, os_ = attached(pj.get("overlays"), seg["id"], win, "from")
    rows = {"beats": [pj["beats"][i] for i in bi], "overlays": [pj["overlays"][i] for i in oi]}
    st = {"id": seg["id"], "t0": round(win[0], 3), "t1": round(win[1], 3), "line": seg.get("line", ""),
          "look": look, "timing": timing, "rows": rows, "spanning": {"beats": len(bs), "overlays": len(os_)},
          "level": seg_level(seg, pj)}
    st["sig"] = sig({"look": look, "rows": rows})
    return st


def all_states(proj, edl=None, pj=None):
    edl = edl if edl is not None else edl_of(proj)
    pj = pj if pj is not None else load(proj, "project.json", {})
    win = windows(proj, edl)
    return [beat_state(proj, s, win[s["id"]], pj) for s in edl]


# ------------------------------------------------------------------------------------------- rounds on disk
def round_numbers(proj):
    d = rdir(proj)
    return sorted(int(p.name[1:]) for p in d.glob("r*") if p.is_dir() and p.name[1:].isdigit()) if d.exists() else []


def round_beats(proj, n):
    p = rdir(proj) / f"r{n}" / "beats.json"
    if not p.exists():
        raise ValueError(f"there is no saved round {n} (saved: {round_numbers(proj) or 'none yet'})")
    return C.read_json(p)


def cmd_snapshot(proj, n, out):
    nums = round_numbers(proj)
    n = n if n is not None else (nums[-1] + 1 if nums else 1)
    d = rdir(proj) / f"r{n}"
    d.mkdir(parents=True, exist_ok=True)
    for name in ("edl.json", "project.json", "segments.json", "words.json", "work/storyboard.json"):
        src = Path(proj) / name
        if src.exists():
            shutil.copyfile(src, d / Path(name).name)
    states = all_states(proj)
    for st in states:
        st["files"] = {}
        for rel in sorted(file_refs({"look": st["look"], "rows": st["rows"]}, proj)):
            blob = archive_file(proj, rel)
            if blob:
                st["files"][rel] = blob
    pj = load(proj, "project.json", {})
    meta = {"round": n, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "level": reel_level(pj),
            "segments": len(states)}
    C.write_json(d / "beats.json", {"round": n, "beats": states})
    C.write_json(d / "meta.json", meta)
    out.log(f"saved round {n}: {len(states)} beats, reel level {meta['level']} -> {d}")
    out.result({"ok": True, "command": "snapshot", **meta, "dir": str(d)})


# ------------------------------------------------------------------------------------------- index / list / diff
def build_index(proj):
    nums = round_numbers(proj)
    cur = all_states(proj)
    hist = {n: {b["id"]: b for b in round_beats(proj, n)["beats"]} for n in nums}
    metas = []
    for n in nums:
        m = load(proj, f"rounds/r{n}/meta.json", {"round": n})
        metas.append({"round": n, "at": m.get("at"), "level": m.get("level")})
    segs = {}
    for b in cur:
        alts = []
        for n in nums:
            old = hist[n].get(b["id"]) or next((x for x in hist[n].values() if base_id(x["id"]) == base_id(b["id"])), None)
            if old and old["sig"] != b["sig"] and not any(a["sig"] == old["sig"] for a in alts):
                alts.append({"round": n, "sig": old["sig"], "level": old.get("level")})
        segs[b["id"]] = {"t": b["t0"], "level": b["level"], "alts": [{"round": a["round"], "level": a["level"]} for a in alts]}
    pj = load(proj, "project.json", {})
    return {"rounds": metas, "reel_level": reel_level(pj), "segs": segs, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def cmd_index(proj, dest, out):
    idx = build_index(proj)
    if dest:
        C.write_json(dest, idx)
        out.log(f"wrote {dest}")
    if out.json or not dest:
        print(json.dumps(idx, ensure_ascii=False))


def diff_rounds(proj, a, b):
    A = {x["id"]: x for x in round_beats(proj, a)["beats"]}
    B = {x["id"]: x for x in round_beats(proj, b)["beats"]}
    rows = []
    for sid in list(dict.fromkeys(list(A) + list(B))):
        x, y = A.get(sid), B.get(sid)
        if not x or not y:
            rows.append({"seg": sid, "change": "added" if y else "removed"})
            continue
        what = [k for k in ("look", "rows", "timing", "level") if json.dumps(x.get(k), sort_keys=True) != json.dumps(y.get(k), sort_keys=True)]
        if what:
            rows.append({"seg": sid, "change": ", ".join(what)})
    return rows


def cmd_list(proj, out):
    nums = round_numbers(proj)
    for i, n in enumerate(nums):
        m = load(proj, f"rounds/r{n}/meta.json", {})
        ch = diff_rounds(proj, nums[i - 1], n) if i else []
        out.log(f"round {n}: {m.get('segments')} beats, level {m.get('level')}" + (f", changed: {', '.join(c['seg'] for c in ch)}" if ch else ""))
    out.result({"ok": True, "command": "list", "rounds": nums})


# ------------------------------------------------------------------------------------------- looks log (snips undo)
def record_look(proj, seg):
    p = Path(proj) / "work" / "beat_looks.json"
    looks = C.read_json(p) if p.exists() else {}
    looks[seg["id"]] = {k: v for k, v in seg.items() if k not in TIMING_KEYS and k not in SKIP_KEYS}
    C.write_json(p, looks)


def reapply_looks(proj, edl, notes=None):
    """after snips.py rebuilt the EDL from the original: put back every look the Room changed (by id, then base id)"""
    p = Path(proj) / "work" / "beat_looks.json"
    if not p.exists():
        return edl
    looks = C.read_json(p)
    out = []
    for s in edl:
        lk = looks.get(s["id"]) or looks.get(base_id(s["id"]))
        if lk:
            s = {**{k: v for k, v in s.items() if k in TIMING_KEYS or k in SKIP_KEYS}, **lk, "id": s["id"]}
            if notes is not None:
                notes.append(f"kept the Room's look on {s['id']}")
        out.append(s)
    return out


# ------------------------------------------------------------------------------------------- levels
def level_keys(lvl, reel, index):
    if lvl == "simple":
        return {"transition": "none", "camera": "still"}
    if lvl == "showreel":
        return {"transition": SHOW_MOVES[index % len(SHOW_MOVES)], "camera": "push"}
    if lvl == "polished" and reel == "showreel":
        return {"transition": "none"}
    if lvl == "polished" and reel == "simple":
        return {"transition": "push"}
    return {}


def set_level(seg, lvl, pj, index):
    m = dict(seg.get("motion") or {}) if isinstance(seg.get("motion"), dict) else {}
    for k in m.pop("from_level", []):
        m.pop(k, None)
    m.pop("level", None)
    if lvl in LEVELS:
        keys = {k: v for k, v in level_keys(lvl, reel_level(pj), index).items() if k not in m}
        m.update(keys, level=lvl)
        if keys:
            m["from_level"] = sorted(keys)
    new = {**seg}
    if m:
        new["motion"] = m
    else:
        new.pop("motion", None)
    return new


def change_level(proj, sid, lvl, edl, pj):
    i = next((k for k, s in enumerate(edl) if s["id"] == sid), None)
    if i is None:
        s = find_seg(edl, sid)
        i = edl.index(s) if s else None
    if i is None:
        raise ValueError(f"no beat called {sid} in the current cut")
    before = seg_level(edl[i], pj)
    edl[i] = set_level(edl[i], lvl, pj, i)
    record_look(proj, edl[i])
    return edl[i]["id"], before, seg_level(edl[i], pj)


def simpler(proj, sid, edl, pj):
    s = find_seg(edl, sid)
    if not s:
        raise ValueError(f"no beat called {sid} in the current cut")
    cur = seg_level(s, pj)
    k = LEVELS.index(cur)
    if k == 0:
        return s["id"], cur, cur, "already Simple. To go calmer, take the graphic off (\"Remove the graphics here\")."
    sid2, a, b = change_level(proj, s["id"], LEVELS[k - 1], edl, pj)
    return sid2, a, b, f"{a.capitalize()} to {b.capitalize()}"


# ------------------------------------------------------------------------------------------- use round N
def shift_row(row, dt, start_key):
    r = copy.deepcopy(row)
    for k in (start_key, "until"):
        if isinstance(r.get(k), (int, float)):
            r[k] = round(r[k] + dt, 3)
    return r


def restore_files(proj, old, n):
    """returns {old path: path to use now}; never overwrites a current file"""
    moved = {}
    for rel, blob in (old.get("files") or {}).items():
        src = rdir(proj) / "blobs" / blob
        cur = Path(proj) / rel
        if cur.is_file() and file_hash(cur) + cur.suffix.lower() == blob:
            continue
        if not src.exists():
            continue
        new_rel = f"assets/rounds/r{n}/{Path(rel).name}"
        (Path(proj) / new_rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, Path(proj) / new_rel)
        moved[rel] = new_rel
    return moved


def repath(obj, moved):
    if not moved:
        return obj
    s = json.dumps(obj, ensure_ascii=False)
    for a, b in moved.items():
        s = s.replace(json.dumps(a)[1:-1], json.dumps(b)[1:-1])
    return json.loads(s)


def use_round(proj, sid, n, edl, pj, timing=False):
    hist = round_beats(proj, n)["beats"]
    old = next((b for b in hist if b["id"] == sid), None) or next((b for b in hist if base_id(b["id"]) == base_id(sid)), None)
    if not old:
        raise ValueError(f"{sid} was not in round {n}")
    s = find_seg(edl, sid)
    if not s:
        raise ValueError(f"no beat called {sid} in the current cut")
    i = edl.index(s)
    moved = restore_files(proj, old, n)
    look = repath(old["look"], moved)
    new = {k: v for k, v in s.items() if k in TIMING_KEYS}
    new.update(look)
    new["id"] = s["id"]
    if timing:
        new.update(old.get("timing") or {})
    edl[i] = {"id": new.pop("id"), **new}
    notes = []
    if old.get("level") in LEVELS and seg_level(edl[i], pj) != old["level"]:
        edl[i] = set_level(edl[i], old["level"], pj, i)      # the reel level moved since: pin the beat to how it was
        notes.append(f"kept it at {old['level'].capitalize()} like round {n}")
    win = windows(proj, edl)[s["id"]]
    dt = win[0] - old["t0"]
    for key, start in (("beats", "at"), ("overlays", "from")):
        rows = list(pj.get(key) or [])
        inside, span = attached(rows, s["id"], windows(proj, edl)[s["id"]], start)
        keep = [r for k, r in enumerate(rows) if k not in inside]
        add = [shift_row(repath(r, moved), dt, start) for r in (old.get("rows") or {}).get(key, [])]
        if inside or add:
            pj[key] = sorted(keep + add, key=lambda r: float(r.get(start, 0)) if isinstance(r.get(start), (int, float)) else 0)
        if span:
            notes.append(f"{len(span)} {key} row(s) run across this and the next beat and were kept as they are")
    record_look(proj, edl[i])
    if moved:
        notes.append(f"brought back {len(moved)} file(s) from round {n} into assets/rounds/r{n}/")
    return s["id"], notes


# ------------------------------------------------------------------------------------------- beat map
def beat_map(proj, edl=None):
    edl = edl if edl is not None else edl_of(proj)
    p = Path(proj) / "work" / "beat_map.json"
    if p.exists():
        bm = C.read_json(p)
        if bm.get("manual"):
            return {int(k): v for k, v in bm["beats"].items()}
    sb = load(proj, "work/storyboard.json", {})
    beats = sb.get("beats", sb) if isinstance(sb, dict) else sb
    beats = beats or []
    out = {i: [] for i in range(len(beats))}
    if not beats:
        return out
    win = windows(proj, edl)
    ts = [float(b.get("t", 0)) for b in beats]
    bw = [set(C.norm(b.get("line", "")).split()) for b in beats]
    k = 0
    for s in edl:
        sw = set(C.norm(s.get("line", "")).split())
        best, score = None, 0.5          # text first (times drift after snips): the beat whose line holds this take
        for i in range(k, min(len(beats), k + 4)):
            sc = len(sw & bw[i]) / max(1, len(sw)) - 0.02 * (i - k)
            if sc > score:
                best, score = i, sc
        if best is None:                  # no text match: fall back to time
            t = win[s["id"]][0] + 0.1
            best = max(k, max([i for i, x in enumerate(ts) if x - 0.25 <= t] or [0]))
        k = best
        out[k].append(s["id"])
    C.write_json(p, {"manual": False, "beats": {str(k): v for k, v in out.items()}})
    return out


# ------------------------------------------------------------------------------------------- apply Room docs
def storyboard_hash(proj):
    import hash as H
    sb = load(proj, "work/storyboard.json", None)
    if sb is None:
        return None
    return H.hash_beats(sb["beats"] if isinstance(sb, dict) else sb)


def apply_doc(proj, doc):
    edl = edl_of(proj)
    pj = load(proj, "project.json", {})
    before = {s["id"]: sig(s) for s in edl}
    pj_before = sig(pj)
    timing_moved, results, notes = False, [], []
    mc = doc.get("motion_choice") or {}
    if mc.get("level") in LEVELS and reel_level(pj) != mc["level"]:
        m = pj.get("motion") if isinstance(pj.get("motion"), dict) else {}
        pj["motion"] = {**m, "level": mc["level"]}
        notes.append(f"reel motion level is now {mc['level']}")
    mb = doc.get("motion_beats") or {}
    if mb.get("levels") is not None:
        h = storyboard_hash(proj)
        if mb.get("for") and h and mb["for"] != h:
            notes.append("per-beat motion levels were set on an older storyboard; skipped them (ask the user to set them again)")
        else:
            bm = beat_map(proj, edl)
            st = load(proj, "rounds/state.json", {}) or {}
            prev = st.get("beat_levels", {})
            want = {str(k): v for k, v in mb["levels"].items() if v in LEVELS}
            for k in sorted(set(prev) | set(want), key=int):
                lvl = want.get(k, "reel")
                if prev.get(k) == want.get(k):
                    continue
                for sid in bm.get(int(k), []):
                    change_level(proj, sid, lvl, edl, pj)
                notes.append(f"beat {int(k) + 1}: {lvl if lvl != 'reel' else 'follows the reel'}")
            st["beat_levels"] = want
            C.write_json(rdir(proj) / "state.json", st)
    for ch in doc.get("beat_changes") or []:
        if ch.get("status", "pending") != "pending":
            continue
        try:
            kind, sid = ch.get("kind"), str(ch.get("seg"))
            if kind == "use_round":
                sid2, nn = use_round(proj, sid, int(ch["from_round"]), edl, pj, timing=bool(ch.get("timing")))
                timing_moved |= bool(ch.get("timing"))
                msg = f"{sid2} is back to its round {ch['from_round']} version" + ("; " + "; ".join(nn) if nn else "")
            elif kind == "simpler":
                sid2, a, b, msg = simpler(proj, sid, edl, pj)
                msg = f"{sid2}: {msg}"
            elif kind == "level":
                sid2, a, b = change_level(proj, sid, ch.get("level", "reel"), edl, pj)
                msg = f"{sid2}: {a.capitalize()} to {b.capitalize()}"
            else:
                raise ValueError(f"unknown change '{kind}'")
            results.append({"id": ch.get("id"), "ok": True, "message": msg})
        except (ValueError, KeyError, TypeError) as e:
            results.append({"id": ch.get("id"), "ok": False, "message": str(e)})
    C.write_json(Path(proj) / "edl.json", edl)
    if sig(pj) != pj_before:
        C.write_json(Path(proj) / "project.json", pj)
    changed = [s["id"] for s in edl if before.get(s["id"]) != sig(s)]
    reel_changed = sig(pj) != pj_before
    rebuild = "assemble" if timing_moved else ("render" if changed or reel_changed else "nothing")
    return {"ok": True, "command": "apply", "results": results, "changed": changed, "reel_changed": reel_changed,
            "rebuild": rebuild, "notes": notes}


# ------------------------------------------------------------------------------------------- cli
def single(proj, fn, out):
    edl = edl_of(proj)
    pj = load(proj, "project.json", {})
    res = fn(edl, pj)
    C.write_json(Path(proj) / "edl.json", edl)
    C.write_json(Path(proj) / "project.json", pj)
    return res


def main():
    ap = argparse.ArgumentParser(description="Per-beat rounds archive, go-back and motion levels.")
    ap.add_argument("project")
    ap.add_argument("cmd", choices=["snapshot", "list", "index", "use", "simpler", "level", "reel-level", "beatmap", "apply", "diff"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--round", type=int)
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = C.Out(a.json)
    proj = C.need_project(a.project, ["edl.json"], a.json)
    try:
        run(proj, a, out)
    except (ValueError, KeyError, FileNotFoundError) as e:
        C.fail(str(e).strip("'"), "Run `rounds.py <project> index` to see the beats and saved rounds.", a.json)


def need(a, n, usage):
    if len(a.args) < n:
        C.fail("Missing arguments.", f"Usage: rounds.py <project> {usage}", a.json)


def run(proj, a, out):
    c = a.cmd
    if c == "snapshot":
        return cmd_snapshot(proj, a.round, out)
    if c == "list":
        return cmd_list(proj, out)
    if c == "index":
        return cmd_index(proj, a.out, out)
    if c == "diff":
        need(a, 2, "diff <a> <b>")
        rows = diff_rounds(proj, int(a.args[0]), int(a.args[1]))
        for r in rows:
            out.log(f"{r['seg']:10} {r['change']}")
        return out.result({"ok": True, "command": "diff", "changes": rows})
    if c == "beatmap":
        bm = beat_map(proj)
        for k, v in bm.items():
            out.log(f"beat {k + 1}: {', '.join(v) or '(none)'}")
        return out.result({"ok": True, "command": "beatmap", "beats": {str(k): v for k, v in bm.items()}})
    if c == "reel-level":
        need(a, 1, "reel-level <simple|polished|showreel>")
        res = apply_doc(proj, {"motion_choice": {"level": a.args[0]}})
    elif c == "use":
        need(a, 2, "use <seg> <round> [--timing]")
        res = apply_doc(proj, {"beat_changes": [{"id": "cli", "kind": "use_round", "seg": a.args[0], "from_round": int(a.args[1]), "timing": a.timing}]})
    elif c == "simpler":
        need(a, 1, "simpler <seg>")
        res = apply_doc(proj, {"beat_changes": [{"id": "cli", "kind": "simpler", "seg": a.args[0]}]})
    elif c == "level":
        need(a, 2, "level <seg> <simple|polished|showreel|reel>")
        res = apply_doc(proj, {"beat_changes": [{"id": "cli", "kind": "level", "seg": a.args[0], "level": a.args[1]}]})
    else:
        need(a, 1, "apply <file.json>")
        res = apply_doc(proj, C.read_json(Path(a.args[0]).expanduser()))
    for r in res["results"]:
        out.log(("done: " if r["ok"] else "could not: ") + r["message"])
    for n in res["notes"]:
        out.log("note: " + n)
    out.log(f"changed beats: {', '.join(res['changed']) or 'none'}; rebuild: {res['rebuild']}")
    out.result(res)
    if any(not r["ok"] for r in res["results"]) and len(res["results"]) == 1 and res["results"][0]["id"] == "cli":
        sys.exit(1)


if __name__ == "__main__":
    main()
