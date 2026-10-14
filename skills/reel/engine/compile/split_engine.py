"""Writer shared by the split-engine styles (split-deck, motion-editorial): edl.json shot fields + project.json settings.

Only the fields the compiler owns are replaced (common.OWNED_*): takes, in/out, lines, locks, waivers (joins_ok,
gaps_ok, segments_ok), grade and face fixes are never touched. The first compile keeps the originals in
work/edl.before-compile.json and work/project.before-compile.json.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .common import OWNED_EDL_KEYS, OWNED_PROJECT_KEYS, backup_once, jload, jwrite

# The house calm defaults: polished motion, plain caption swaps (no word pops), light SFX, no grain, no handheld drift
# calm (default): level simple (settle only, no punch-ins or reframes, density gates exempt) plus soft transitions
# on section cuts; the house rule beats the density targets: never add zooms to make a reel look busy.
# polished: the engine's full teaching-pace system (punches, reframes, density gates), captions still plain.
MOTION_PRESETS = {
    "calm": {"level": "simple", "sfx": "light", "captions": "plain", "grain": False, "handheld": False,
             "transitions": {"per10s": 2.0, "moves": ["push", "zoom"]}},
    "polished": {"level": "polished", "sfx": "light", "captions": "plain", "transitions": "auto", "grain": False,
                 "handheld": False},
}
MOTION = MOTION_PRESETS["calm"]
PUNCH = 1.12        # framing change for a jump cut between two caption-only full shots (thought-break size)


def punch_runs(rows: list) -> list:
    """Caption-only full shots in a row would be invisible jump cuts: every other one gets a punch-in.
    rows: [{"id", "mode", "top"}] in edl order -> new rows with "punch" set where needed."""
    out, prev_plain, flip = [], False, False
    for r in rows:
        plain = r["mode"] == "full" and not r.get("top")
        flip = (not flip) if (plain and prev_plain) else False
        out.append({**r, **({"punch": PUNCH} if plain and flip else {})})
        prev_plain = plain
    return out


def calm_talk(rows: list) -> list:
    """Caption-only talking shots run at motion level simple (settle only: no punch-ins, reframes or transitions
    into them, density targets relaxed for their span); the graphic beats carry the motion. The house rule: never add
    zooms to make a talking stretch look busy."""
    return [{**r, "motion": {"level": "simple"}} if r["mode"] == "full" and not r.get("top") else r for r in rows]


def edl_with(edl: list, rows: list) -> list:
    """edl.json with the compiler's shot fields swapped in (everything else kept)."""
    by_id = {r["id"]: r for r in rows}
    out = []
    for e in edl:
        base = {k: v for k, v in e.items() if k not in OWNED_EDL_KEYS}
        r = by_id.get(e["id"], {"mode": "full"})
        shot = {k: r[k] for k in OWNED_EDL_KEYS if r.get(k) not in (None, "")}
        out.append({**base, **shot})
    return out


def project_with(pj: dict, patch: dict) -> dict:
    base = {k: v for k, v in pj.items() if k not in OWNED_PROJECT_KEYS}
    return {**base, **patch}


def hold_gap(pj: dict, default: float = 0.4) -> float:
    return float((pj.get("captions") or {}).get("hold_gap", default))


def write(proj, edl: list, rows: list, patch: dict, report: dict) -> dict:
    """Back up once, then write edl.json and project.json. Returns the 'compiled' record stored in project.json."""
    backup_once(proj / "edl.json", proj / "work" / "edl.before-compile.json")
    backup_once(proj / "project.json", proj / "work" / "project.before-compile.json")
    compiled = {**report, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    jwrite(proj / "edl.json", edl_with(edl, rows))
    jwrite(proj / "project.json", project_with(jload(proj / "project.json", {}), {**patch, "compiled": compiled}))
    return compiled
