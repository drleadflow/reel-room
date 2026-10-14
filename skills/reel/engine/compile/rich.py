"""Rich top slot for the split-engine adapters: colour sets that change per plan section (cream, dark, tan, the way
the showcase showcase reels shift), and hero spans (a split-panel hero borrows the caption-only lines just before it
in the same section, so a hero on a 0.5 s line still gets the window it needs to build).
"""
from __future__ import annotations

import hero_schema as HS

TONES = ("dark", "cream", "tan")
TITLE_STAMP_CAP = 4      # 2026-10-13: at most 4 big serif headlines per reel; the rest become calm cards
PURPOSE_SCORE = {"hook": 30, "proof": 15, "promise": 10, "cta": 8, "explain": 4, "transition": 0}
SPAN_MAX_ROWS, SPAN_MAX_SECS, SPAN_PAD = 3, 6.0, 0.8


def section_tones(shots: list) -> dict:
    """{section name: colour set}, cycling dark -> cream -> tan in order of first appearance."""
    out = {}
    for _, s in shots:
        sec = s.get("section") or "_"
        if sec not in out:
            out[sec] = TONES[len(out) % len(TONES)]
    return out


def tone_of(shot: dict, tones: dict) -> str:
    return tones.get(shot.get("section") or "_", TONES[0])


def _plain(row: dict) -> bool:
    return row["mode"] == "full" and not row.get("top")


def extend_spans(rows: list, shots: list, wins: dict | None) -> list:
    """Split-panel heroes take the caption-only rows before them (same section) until they have their window.
    rows: [{"id", "mode", "top"}] in edl order; returns new rows (first row of a span carries the hero, the rest
    'same' so the split engine keeps one beat across the cuts)."""
    if not wins:
        return rows
    rows = [dict(r) for r in rows]
    for i, (sid, shot) in enumerate(shots):
        if shot.get("kind") != "hero" or rows[i]["mode"] != "split" or i == 0:
            continue
        need = HS.HEROES[shot["hero_id"]]["min_secs"] + SPAN_PAD
        t0, t1 = wins[sid]
        j = i
        while (t1 - t0 < need and j - 1 > 0 and i - (j - 1) <= SPAN_MAX_ROWS and _plain(rows[j - 1])
               and shots[j - 1][1].get("section") == shot.get("section")
               and t1 - wins[shots[j - 1][0]][0] <= SPAN_MAX_SECS):
            j -= 1
            t0 = wins[shots[j][0]][0]
        if j == i:
            continue
        top = rows[i]["top"]
        rows[j] = {**rows[j], "mode": "split", "top": top, "span": [shots[k][0] for k in range(j, i + 1)]}
        for k in range(j + 1, i + 1):
            rows[k] = {**rows[k], "mode": "split", "top": "same"}
    return rows


def _is_stamp(top) -> bool:
    return isinstance(top, dict) and top.get("insert") == "hero" and top.get("args", {}).get("comp") == "title-stamp"


def _stamp_score(i: int, shot: dict, top: dict, section_last: set) -> float:
    """Hook first, then hero beats, payoff lines (the last graphic of a section), proof/promise lines, short punchy text."""
    if i == 0:
        return 1000.0
    text = top["args"].get("text", "")
    return (60 * bool(shot.get("hero")) + PURPOSE_SCORE.get(shot.get("purpose") or "", 0)
            + 20 * (i in section_last) + max(0, 14 - len(text)) * 0.5)


def cap_title_stamps(rows: list, shots: list, calm, limit: int = TITLE_STAMP_CAP) -> list:
    """Keep the `limit` strongest title-stamps; calm(shot, args) -> the replacement top for the rest."""
    cands = [i for i, r in enumerate(rows) if _is_stamp(r.get("top"))]
    if len(cands) <= limit:
        return rows
    last = {}
    for i, r in enumerate(rows):
        if r.get("top") and r["top"] != "same":
            last[shots[i][1].get("section")] = i
    keep = set(sorted(cands, key=lambda i: -_stamp_score(i, shots[i][1], rows[i]["top"], set(last.values())))[:limit])
    return [{**r, "top": calm(shots[i][1], r["top"]["args"])} if i in cands and i not in keep else r
            for i, r in enumerate(rows)]
