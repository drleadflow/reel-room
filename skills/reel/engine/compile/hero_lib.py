"""Library heroes for hero beats: a fast model picks one hero from the catalogue for the beat's idea and fills its typed
contract from the line; engine/hero_schema.py validates it (words and numbers spoken, anchors in the line, brand
colour sets, citations from the project's own sources). The compiler then adds the data a model never writes
(the project's cuts for nle-timeline, stills of the creator's own footage for orbit / grid / palette tiles).
A beat with no fitting hero ("none") keeps the kit fallback in heroes.py.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import hero_schema as HS
import llm_router as LR

CHAIN = (LR.ROUTER, LR.FAST)
STYLE_LAYOUTS = {"split-deck": ("split", "full"), "motion-editorial": ("card", "stage", "full"),
                 "editorial-ui": ("full", "overlay")}


# editorial-ui room cuts have no band above a high head for big UI heroes; its heroes are the behind-the-head family
# (cut-out matte), everything else becomes a colour-set headline or an everyday card (compile/editorial_ui.py)
STYLE_ONLY = {"editorial-ui": ("word-stamp", "magazine-cover", "reel-orbit")}
# 2026-10-14: editorial-ui also draws the data heroes on their own colour set (upper third, never over the face) and
# the title-stamp as a set headline (compile/eui_data.py), so the planner's charts and counters are no longer dropped
SET_HEROES = {"editorial-ui": ("evidence-hero", "money-counter", "title-stamp")}
STYLE_ONLY = {k: v + SET_HEROES.get(k, ()) for k, v in STYLE_ONLY.items()}


def allowed(style: str, sources: str, secs: float | None = None) -> list:
    """Hero ids this style can draw (and the project can feed: evidence needs sources) in a window of `secs`."""
    lays = STYLE_LAYOUTS.get(style, ("split",))
    only = STYLE_ONLY.get(style)
    out = []
    for hid, c in HS.HEROES.items():
        if not (set(c["layouts"]) & set(lays) or hid in SET_HEROES.get(style, ())) or (only and hid not in only):
            continue
        if "sources" in c["needs"] and not sources.strip():
            continue
        if secs is not None and c["min_secs"] > secs + 4.0:      # a split hero can borrow the lines before it
            continue
        out.append(hid)
    return out


def prompt(beat: dict, ids: list, context: str, secs: float, suggested: str | None = None) -> str:
    hint = f"\nThe planner suggested the library hero {suggested!r}; use it unless it really does not fit." \
        if suggested in ids else ""
    return f"""A reel has a planned hero moment. Pick the ONE library hero that best realises the idea and fill its
fields from the line, or answer "none" when nothing in the library fits.
Hero idea: {beat['visual_intent']}
THIS LINE: {beat['line']}
Neighbouring lines: {context}
The hero has about {secs:.1f} s on screen (its line plus the caption-only lines just before it); pick a hero whose
"needs" fits that window (a window up to 0.5 s shorter still works: heroes compress). Anchors still come from
THIS LINE.{hint}

Library:
{HS.catalog_text(ids)}

{HS.TIMING}

Rules: every on-screen word and number is copied from THIS LINE or the neighbouring lines (never invent stats, labels,
titles or claims); anchors are '@word' using a word of THIS LINE, in spoken order; omit fields you do not need; no em
dashes; tone is a colour set. JSON only:
{{"hero": one of {ids} or "none", "args": {{...}}, "why": "max 12 words"}}"""


def ask(beat: dict, ids: list, context: str, sources: str, secs: float, suggested: str | None = None) -> dict:
    """{"hero", "args", "source": "llm", "cost"} or {"hero": "none", ...}; never raises."""
    try:
        res = LR.typed(prompt(beat, ids, context, secs, suggested), HS.validator(ids, beat["line"], context, sources),
                       CHAIN, 900)
    except LR.LLMError as exc:
        return {"hero": "none", "note": str(exc)}
    cost = round(sum(a["cost"] or 0 for a in res["attempts"]), 5)
    if res["data"] is None:
        return {"hero": "none", "note": res["attempts"][-1]["error"], "cost": cost}
    d = res["data"]
    return {"hero": d.get("hero", "none"), "args": d.get("args") or {}, "why": d.get("why", ""), "source": "llm",
            "cost": cost}


def sources_text(proj: Path) -> str:
    """The project's own citations: script.md + work/sources.txt (empty when the creator gave none)."""
    out = []
    for rel in ("script.md", "work/sources.txt"):
        p = proj / rel
        if p.exists():
            out.append(p.read_text(errors="ignore"))
    return "\n".join(out)


def _reels(proj: Path, n: int) -> list:
    """The creator's own reel thumbnails: <project>/assets/reels/*.jpg, else brand.json "reels_dir" (copied into the
    project). Empty when the creator has none."""
    own = sorted((proj / "assets" / "reels").glob("*.jpg")) if (proj / "assets" / "reels").exists() else []
    if len(own) >= 3:
        return [str(p.relative_to(proj)) for p in own[:n]]
    try:
        brand = json.loads((Path.home() / ".reel-room" / "brand.json").read_text())
    except (OSError, ValueError):
        brand = {}
    src = Path(str(brand.get("reels_dir", ""))).expanduser() if brand.get("reels_dir") else None
    if not src or not src.is_dir():
        return []
    files = sorted(src.glob("*.jpg"))[:n]
    dest = proj / "assets" / "reels"
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copyfile(f, dest / f.name)
    return [f"assets/reels/{f.name}" for f in files]


def _stills(proj: Path, name: str, times: list) -> list:
    """Stills of the creator's own A-roll at the given cut seconds (360x640)."""
    out_dir = proj / "assets" / "hero"
    out_dir.mkdir(parents=True, exist_ok=True)
    rels = []
    for i, t in enumerate(times):
        dest = out_dir / f"{name}{i}.jpg"
        if not dest.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(proj / "assets" / "aroll.mp4"),
                            "-frames:v", "1", "-vf", "scale=360:640", "-q:v", "4", str(dest)], check=False)
        if dest.exists():
            rels.append(f"assets/hero/{dest.name}")
    return rels


def _pick(proj: Path, name: str, n: int, total: float) -> list:
    return _reels(proj, n) or _stills(proj, name, [total * (i + 0.5) / n for i in range(n)])


def data_for(proj: Path, hid: str, inp: dict, beats: list) -> dict:
    """Compiler-filled fields (never from the model)."""
    win = inp["win"]
    total = max(t1 for _, t1 in win.values())
    if hid == "nle-timeline":
        cuts = sorted(t0 for t0, _ in win.values() if t0 > 0.05)
        blocks = [list(win[b["id"]]) for b in beats if b.get("component") not in (None, "none") and b["id"] in win]
        thumbs = _stills(proj, "nle", [(a + b) / 2 for a, b in zip([0.0] + cuts, cuts + [total])][::max(1, len(cuts) // 9)][:10])
        return {"span": [0.0, round(total, 3)], "cuts": cuts, "blocks": blocks, "thumbs": thumbs}
    if hid == "reel-orbit":
        return {"media": _pick(proj, "orbit", 6, total)}
    if hid == "grid-collapse":
        return {"tiles": _pick(proj, "grid", 8, total)}
    if hid == "video-card":
        clips = _reels(proj, 4)
        return {"clips": clips} if clips else {}
    if hid == "palette-fan":
        return {"items": _pick(proj, "palette", 5, total), "looks": True}
    return {}
