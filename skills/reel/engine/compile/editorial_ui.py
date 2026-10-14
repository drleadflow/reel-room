"""editorial-ui adapter: plan -> the editorial-ui content contract (project.json "editorial", README of
templates/editorial-ui) + the cut-out need list (work/cutout_need.json) for pipeline.py's parallel cut-out.

  hook + the strongest word beats (title-stamp cap 4, hook included) -> "set": cut-out on the section's colour set,
    the phrase as a huge serif headline BEHIND the head (italic sub-line = the speaker's next words)
  word / list / stat / flow -> "room" + an everyday editorial card (compile/everyday.py: ed-headline, ed-kicker,
    ed-checklist, ed-number, ed-contrast) in the band above the head, else under the chin
  typer -> "room" + the native prompt card (types the words)      cta -> "room" + kit comment-cta card
  hero  -> "room" + the library hero over the footage; word-stamp / magazine-cover / reel-orbit get a cut-out matte
    span so the type sits BEHIND the head (cutout_cache.span_webm, cached per A-roll)
  none / phone -> "room" (caption only)
Colour sets per plan section (dark, cream, tan, accent) come from brand.json through the kit's colour_set(), written
as editorial palette keys, so the set plates and the kit cards share one palette. Caps: <= 4 set headlines (hook
included), <= 5 heroes (extra hero beats become everyday cards).
"""
from __future__ import annotations

import json
from pathlib import Path

import hero_schema as HS

from . import eui_data as ED
from . import everyday as E
from . import rich as R
from .common import norm, title_lines
from .split_engine import MOTION_PRESETS

STYLE = "editorial-ui"
HERO_COMPONENTS = ["label-pill", "checklist-tick", "odometer", "typer", "before-after", "comment-cta", "stepper"]
SET_CAP, HERO_CAP = 4, 5
HERO_HOLD = 3.4              # s: a hero may run on through caption-only cuts until its stamp has been read
HEADLINE_MAX_W = 880          # set headlines stay inside the safe sides when centred on an off-centre face
ACCENT_MUTE = 0.35           # the accent set plate is the brand accent toned toward ink (a raw brand green reads as chroma)
CARD_TONE = "cream"           # room callouts stay light (judge: dark cards on a night sky read low-contrast)
CARD_MIN_SECS = 1.2          # a cut shorter than this gets no card (it would only flash)
SET_MIN_SECS = 1.2           # a colour-set cut shorter than this reads as a flash, not a beat
LINE_MAX = 11                # headline chars per line before it splits on a word (the band above the head is short)
MATTE_HEROES = ("word-stamp", "magazine-cover", "reel-orbit")
TONE_KEYS = ("dark", "cream", "tan", "accent")
FPS, PAD_F = 30, 8           # matte spans cover the hero window plus a few frames (the renderer's coverage gate)
BAKE_WORKERS = 3             # cached per-cut bake (templates/editorial-ui/bake_cache.py), shared-machine cap


def palette(brand: dict) -> dict:
    """{dark, cream, tan, accent: {plate, type, accent}} from brand.json via the kit's colour sets (one palette)."""
    from heroes_base import colour_set     # templates/kit is on sys.path through hero_schema
    from rrkit_base import mix
    k = type("K", (), {"brand": brand})()
    out = {t: {"plate": colour_set(k, t)["g"], "type": colour_set(k, t)["ink"], "accent": colour_set(k, t)["acc"]}
           for t in TONE_KEYS}
    out["accent"]["plate"] = mix(brand["colors"]["accent"], brand["colors"]["ink"], ACCENT_MUTE)   # judge: raw green
    return out


def _two(text: str) -> str:
    """A long phrase on 2 balanced lines ('VISUAL|PALETTE'), words verbatim."""
    if len(text) <= LINE_MAX or len(text.split()) < 2:
        return text
    return "|".join(title_lines(text))


def headline_text(shot: dict, line: str) -> str:
    """'TEXT', 'TEXT|_sub_' (the italic accent line is the speaker's next words, or the text after '|'), or a long
    phrase on 2 lines (then no sub-line: the band above the head holds 2 lines)."""
    text = shot["text"]
    if "|" in text:
        a, b = (x.strip() for x in text.split("|", 1))
        return f"{a.upper()}|_{b}_" if len(a) <= LINE_MAX else _two(a.upper())
    main = _two(text.upper())
    sub = E.sub_of(text, line)
    return f"{main}|_{sub}_" if sub and len(sub) <= 18 and "|" not in main else main


def pick_sets(shots: list, wins: dict | None = None) -> set:
    """Indices that go on the colour set: the hook (0) plus the best word beats, SET_CAP in all (same ranking as the
    split-deck title-stamp cap: hero, purpose, section payoff, short punchy text)."""
    last = {}
    for i, (_sid, s) in enumerate(shots):
        if s["kind"] != "none":
            last[s.get("section")] = i
    long_ = (lambda sid: wins[sid][1] - wins[sid][0] >= SET_MIN_SECS) if wins else (lambda sid: True)
    cands = [i for i, (sid, s) in enumerate(shots) if i > 0 and s["kind"] == "word"
             and len(s["text"].split("|")[0].strip() if s.get("stamp") else s["text"]) <= 28 and long_(sid)]
    score = {i: R._stamp_score(i, shots[i][1], {"args": {"text": shots[i][1]["text"]}}, set(last.values()))
             + (500 if shots[i][1].get("stamp") else 0) for i in cands}     # planner title-stamps first
    return {0} | set(sorted(cands, key=lambda i: -score[i])[:SET_CAP - 1])


def cap_heroes(shots: list, notes: list | None = None) -> list:
    """Hero beats past HERO_CAP (in order), or with a hero this style does not draw, become word shots on their
    anchor word (a spoken word, so it validates). Every conversion is a note (never silent)."""
    from .hero_lib import STYLE_ONLY
    out, n, notes = [], 0, notes if notes is not None else []
    for sid, s in shots:
        if s["kind"] == "hero" and s["hero_id"] not in STYLE_ONLY[STYLE]:     # a cached pick from another style
            notes.append(f"beat {sid}: {s['hero_id']} is not drawn by {STYLE}, shown as an everyday word card")
            s = {**s, "kind": "word", "text": (s.get("anchor") or "@")[1:] or s["comp"], "hero": True}
        if s["kind"] == "hero":
            n += 1
            if n > HERO_CAP:
                notes.append(f"beat {sid}: {s['hero_id']} is hero {n} (cap {HERO_CAP}), shown as an everyday word card")
                s = {**s, "kind": "word", "text": (s.get("anchor") or "@")[1:] or s["comp"], "hero": True}
        out.append((sid, s))
    return out


def _with_at(bid: str, args: dict, line: str, context: str) -> dict:
    """A room card lands on its first visible word (the showcase's cards arrive with the words, not on the cut)."""
    import beat_schema as BS
    import plan_schema as PS
    first = {"ed-contrast": args.get("left"), "ed-checklist": (args.get("items") or [""])[0]}.get(bid) or ""
    tok = norm(first.split()[0]) if first.split() else ""
    tok = "" if tok in PS.STOP else tok          # 'to', 'the' match an earlier word: land on the payoff instead
    at = f"@{tok}" if tok and tok in {norm(w) for w in line.split()} else \
        args.get("land") or (args.get("ticks") or [None])[0]
    cand = {**args, "at": at} if at else args
    return cand if BS.validate(bid, cand, line, context) is None else args


def card_for(shot: dict, line: str, context: str, tone: str, avoid: str | None = None):
    """The room card for one shot (None = caption only). avoid: the previous card's type (rotate treatments)."""
    k = shot["kind"]
    if k in ("word", "list", "stat", "flow"):
        got = E.build(shot, line, context, avoid)
        return {"kind": "beat", "comp": got[0], "args": {**_with_at(got[0], got[1], line, context), "tone": CARD_TONE}} \
            if got else None
    if k == "typer":
        return {"kind": "prompt", "at": 0.15, "text": shot["text"]}
    if k == "cta":                    # the native status pill fits the short band above a high head
        from .items import keyword_of
        kw = keyword_of(shot["text"], shot.get("anchor"))
        label = "COMMENT" if "comment" in {norm(w) for w in line.split()} else ""
        return {"kind": "status", "at": shot.get("anchor") or 0.2, "label": label, "text": kw}
    if k == "source":                 # an evidence citation without its chart (compile/eui_data.py)
        return {"kind": "status", "at": shot.get("anchor") or 0.2, "label": "SOURCE", "text": shot["text"]}
    if k == "phone" and shot.get("text"):    # no phone frame in this style: its title as an everyday card
        return card_for({**shot, "kind": "word"}, line, context, tone, avoid)
    if k == "hero":
        return {"kind": "hero", "comp": shot["hero_id"], "args": {**shot["args"], "tone": tone},
                "matte": shot["hero_id"] in MATTE_HEROES}
    return None


def hook_headline(title: str, shot: dict, line: str) -> str:
    l1, l2 = title_lines(title)
    if l1 and l2:
        return f"{l1.upper()}|_{l2}_"
    return (l1 or "").upper() or headline_text({**shot, "text": shot.get("text") or line.split(",")[0][:18]}, line)


def _plain_room(beats: dict, sid: str) -> bool:
    b = beats.get(sid) or {}
    return b.get("scene") == "room" and not b.get("cards")


def hero_start(i: int, shots: list, wins: dict, beats: dict) -> int:
    """A hero may start in the caption-only room cuts just before it (same section) until it has its window."""
    sid, s = shots[i]
    need = HS.HEROES[s["hero_id"]]["min_secs"] + R.SPAN_PAD
    t0, t1 = wins[sid]
    j = i
    while (t1 - t0 < need and j - 1 > 0 and i - (j - 1) <= R.SPAN_MAX_ROWS and _plain_room(beats, shots[j - 1][0])
           and shots[j - 1][1].get("section") == s.get("section") and t1 - wins[shots[j - 1][0]][0] <= R.SPAN_MAX_SECS):
        j -= 1
        t0 = wins[shots[j][0]][0]
    return j


def _frames(win) -> list:
    return [int(round(win[0] * FPS)), int(round(win[1] * FPS))]


def editorial_beats(shots: list, lines: dict, title: str, wins: dict) -> tuple:
    """-> (beats config, cut-out need spans, notes)."""
    tones, sets, ids = R.section_tones(shots), pick_sets(shots, wins), list(lines)
    beats, need, notes = {}, [], []
    n_set, prev = 0, None
    for i, (sid, s) in enumerate(shots):
        tone = R.tone_of(s, tones)
        if s.get("data_set"):  # a data hero on its own colour set, upper third (compile/eui_data.py)
            tone, n_set = TONE_KEYS[n_set % len(TONE_KEYS)], n_set + 1
            card = {"kind": "hero", "comp": s["hero_id"], "args": {**s["args"], "tone": tone}, "matte": False,
                    "data": True}
            beats[sid] = {"scene": "set", "set": tone, "zoom": 1.0, "headlines": [], "cards": [card]}
            need.append(_frames(wins[sid]))
            prev = s["hero_id"]
            continue
        if i in sets:          # consecutive sets never share a colour (the showcase: dark -> cream -> tan -> accent)
            tone, n_set = TONE_KEYS[n_set % len(TONE_KEYS)], n_set + 1
            text = hook_headline(title, s, lines[sid]) if i == 0 else headline_text(s, lines[sid])
            beats[sid] = {"scene": "set", "set": tone, "headlines": [{"at": 0, "text": text}]}
            need.append(_frames(wins[sid]))
            continue
        k = ids.index(sid)
        ctx = " ".join(lines[j] for j in ids[max(0, k - 1):k + 2] if j != sid)
        short = wins[sid][1] - wins[sid][0] < CARD_MIN_SECS and s["kind"] in ("word", "list", "stat", "flow")
        card = None if short else card_for(s, lines[sid], ctx, tone, prev)
        prev = (card or {}).get("comp", prev)
        beats[sid] = {"scene": "room", "cards": [card] if card else []}
        if s["kind"] != "none" and not card:
            why = f"its cut is under {CARD_MIN_SECS} s" if short else "no editorial treatment validates"
            notes.append(f"beat {sid}: {s.get('comp') or s['kind']} ({s['kind']}) not drawn ({why}), caption only")
        if card and card["kind"] == "hero":
            j = hero_start(i, shots, wins, beats)
            if j < i:
                beats[sid] = {"scene": "room", "cards": []}
                beats[shots[j][0]] = {"scene": "room", "cards": [{**card, "end_seg": sid}]}
    return beats, need + hero_tails(shots, wins, beats), notes


def hero_tails(shots: list, wins: dict, beats: dict) -> list:
    """A hero holds its built word past a short cut: it runs on into the caption-only room cuts after it (up to
    HERO_HOLD s in all), so it never outlives its cut-out matte. Returns the matte need spans."""
    ids, need = [sid for sid, _ in shots], []
    for sid in ids:
        for c in (beats.get(sid) or {}).get("cards", []):
            if c.get("kind") != "hero" or c.get("data"):      # data heroes stay inside their own set cut
                continue
            end = c.get("end_seg", sid)
            k = ids.index(end)
            while (k + 1 < len(ids) and wins[ids[k]][1] - wins[sid][0] < HERO_HOLD
                   and _plain_room(beats, ids[k + 1])):
                k += 1
            c["end_seg"] = ids[k]
            if c.get("matte"):
                f0, f1 = _frames((wins[sid][0], wins[ids[k]][1]))
                need.append([f0, f1 + PAD_F])
    return need


def project_patch(pj: dict, plan: dict, beats: dict, brand: dict, first_tone: str) -> dict:
    l1, l2 = title_lines(plan.get("title", ""))
    hook = {"l1": l1, "l2": l2, "category": (pj.get("hook") or {}).get("category", "plan")}
    ed = {"beats": beats, "palette": palette(brand), "set": {"default": first_tone, "edge": {"fg_half": True}},
          "headline": {"max_w": HEADLINE_MAX_W},
          "takeover": {"auto": False}, "matte": {"source": "cache"}, "bake": {"workers": BAKE_WORKERS, "cache": True},
          "loop": {"t0": 0.0}, "poster": {"t": 1.2}}
    motion = {**MOTION_PRESETS["calm"], "transitions": {"per10s": 2.0, "moves": ["push"]}}   # no blur zooms
    return {"style": STYLE, "template": STYLE, "motion": motion, "hook": hook, "beats": [], "editorial": ed}


def compile_project(proj: Path, inp: dict, plan: dict, shots: list, report: dict) -> dict:
    """Write edl.json (shot fields cleared: this style has no split rows), project.json (style + "editorial") and
    work/cutout_need.json. Returns the report additions."""
    import cutout_cache as CC
    from . import split_engine as SE
    from . import validate as V
    lines = V.edl_lines(inp["edl"])
    from .hero_lib import STYLE_ONLY
    ids = list(lines)
    ctx = {"wins": inp["win"], "lines": lines, "facepos": inp.get("facepos") or {}, "sources": ED.sources_txt(proj),
           "context": {sid: " ".join(lines[j] for j in ids[max(0, k - 1):k + 2] if j != sid)
                       for k, sid in enumerate(ids)}}
    shots, sub_notes = ED.route(shots, ctx, STYLE_ONLY[STYLE])
    shots = cap_heroes(shots, sub_notes)
    sub_notes += ED.planner_notes(plan.get("beats", []), {k: {"hero": v} for k, v in
                                                          (report.get("library_heroes") or {}).items()},
                                  STYLE_ONLY[STYLE])
    beats, need, notes = editorial_beats(shots, lines, plan.get("title", ""), inp["win"])
    brand = json.loads((Path.home() / ".reel-room" / "brand.json").read_text())
    if (proj / "brand.json").exists():        # project brand.json wins (same order as templates/editorial-ui/etheme.py)
        own = json.loads((proj / "brand.json").read_text())
        brand = {**brand, **own, "colors": {**brand.get("colors", {}), **own.get("colors", {})},
                 "fonts": {**brand.get("fonts", {}), **own.get("fonts", {})}}
    tones = R.section_tones(shots)
    patch = project_patch(inp["pj"], plan, beats, brand, R.tone_of(shots[0][1], tones))
    rows = [{"id": e["id"], "mode": "full", "top": None} for e in inp["edl"]]
    CC.write_need(proj, need, {"set": sum(1 for b in beats.values() if b["scene"] == "set"),
                               "matte_heroes": sum(1 for b in beats.values() for c in b.get("cards", [])
                                                   if c.get("matte"))})
    extra = {"sets": [sid for sid, b in beats.items() if b["scene"] == "set"],
             "cards": {sid: [c.get("comp", c["kind"]) for c in b["cards"]] for sid, b in beats.items() if b.get("cards")},
             "cutout_frames": sum(b - a for a, b in need), "notes": report.get("notes", []) + sub_notes + notes,
             "data_heroes": [sid for sid, b in beats.items() for c in b.get("cards", []) if c.get("data")]}
    SE.write(proj, inp["edl"], rows, patch, {**report, **extra})
    return extra
