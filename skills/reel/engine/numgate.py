"""The on-screen number gate: every number the compiled project will put on screen must be verified against the audio
(numcheck.py ledger work/numbers.json), confirmed by hand (project.json "numbers_ok"), or, for evidence-hero
fields, come verbatim from the creator's own sources (work/sources.txt).

  scan(proj)            every on-screen number: captions (words.json), set headlines and cards (project.json
                        "editorial"), split-panel inserts (edl.json "top"), project beats, the hook
  unverified(proj)      the ones that fail the rule (with where they are)
  scrub(proj)           compile time: an unverified number is removed (words-only: optional lines dropped, the number
                        cut from the text) or its graphic dropped; every change is returned as a compile note
  check(proj)           qa.py gate "numbers_verified" (qa_more.py): fails loudly when one is still on screen
"""
from __future__ import annotations

import json
from pathlib import Path

import numwords as NW

LEDGER = "work/numbers.json"
OK_STATUS = ("verified", "confirmed")
SCOPE_PAD = 3.0          # s: a graphic may quote a number said up to this far outside its own cut
CAPTION_TOL = 0.6        # s: a caption number matches a ledger entry this close in time
SKIP_KEYS = {"at", "land", "sub_at", "stamp", "stamp_at", "draw", "burn", "pick_at", "play_at", "sticker_at", "marks",
             "lines_at", "chapter_at", "setup_at", "ignite", "fan_at", "label_at", "highlight_at", "strike_at", "a_at",
             "ticks", "until", "end_seg", "send", "done", "tone", "comp", "kind", "matte", "set", "scene", "insert",
             "layout", "size", "z", "track", "media", "clips", "tiles", "thumbs", "src", "span", "cuts", "blocks",
             "looks", "y_max", "hold", "cps", "first_tick_s", "x", "y", "w", "h", "cx", "cy", "bottom", "same",
             "at_word", "seg", "mode", "punch", "punch_at", "motion", "highlight", "id", "category", "layout_hint",
             "arrow", "neq", "bars", "face", "area", "reveal", "subject", "page", "step", "step_at", "zoom"}
OPTIONAL = {"sub", "kicker", "context", "label", "stat_label", "unit", "prefix", "done_text", "meta", "issue", "tag",
            "date", "note"}
SOURCE_FIELDS = {"citation", "series", "labels", "stat", "stat_label", "kicker"}    # evidence-hero only


def _jload(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def onscreen_strings(obj, key: str = ""):
    """(field, text) for every on-screen string in a card / insert / hero args tree (anchors, paths, colours and
    timing keys skipped; numbers in lists like steps / values count)."""
    if key in SKIP_KEYS:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from onscreen_strings(v, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from onscreen_strings(v, key)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        if key in ("steps", "values", "series", "value", "limit", "days", "count"):
            yield key, str(obj)
    elif isinstance(obj, str):
        s = obj.strip()
        if s and not s.startswith(("@", "#")) and not ("/" in s and "." in s.rsplit("/", 1)[-1]):
            yield key, s


def _items(proj: Path, pj: dict, edl: list, wins: dict) -> list:
    """[{where, scope (t0, t1) or None, field, text, hero}] for every graphic string of the compiled project."""
    out = []
    hook = pj.get("hook") or {}
    for k in ("l1", "l2"):
        if hook.get(k):
            out.append({"where": f"hook.{k}", "scope": None, "field": k, "text": str(hook[k]), "hero": None})
    for sid, b in ((pj.get("editorial") or {}).get("beats") or {}).items():
        w = wins.get(sid)
        for i, h in enumerate(b.get("headlines") or []):
            out.append({"where": f"editorial.{sid}.headlines[{i}]", "scope": w, "field": "text",
                        "text": str(h.get("text", "")), "hero": None})
        for i, c in enumerate(b.get("cards") or []):
            end = wins.get(c.get("end_seg"), w) if w else None
            scope = (w[0], end[1]) if w and end else w
            for f, t in onscreen_strings(c):
                out.append({"where": f"editorial.{sid}.cards[{i}]", "scope": scope, "field": f, "text": t,
                            "hero": c.get("comp") if c.get("kind") == "hero" else None})
    for row in edl:
        items = row.get("top") if isinstance(row.get("top"), list) else [row.get("top")] if row.get("top") else []
        for i, it in enumerate(items):
            hero = ((it.get("args") or {}).get("comp") if isinstance(it, dict) else None)
            for f, t in onscreen_strings(it):
                out.append({"where": f"edl.{row.get('id')}.top[{i}]", "scope": wins.get(row.get("id")), "field": f,
                            "text": t, "hero": hero})
    for j, b in enumerate(pj.get("beats") or []):
        for f, t in onscreen_strings(b.get("items") or []):
            out.append({"where": f"beats[{j}]", "scope": wins.get(b.get("seg")), "field": f, "text": t, "hero": None})
    return [x for x in out if NW.has_digits(x["text"])]


def _ok_value(value: str, scope, entries: list) -> bool:
    for e in entries:
        if e["status"] in OK_STATUS and NW.same(e["value"], value):
            if scope is None or (scope[0] - SCOPE_PAD <= e["t0"] <= scope[1] + SCOPE_PAD):
                return True
    return False


def _sources(proj: Path) -> str:
    p = proj / "work" / "sources.txt"
    return p.read_text(errors="ignore") if p.exists() else ""


def _windows(proj: Path) -> dict:
    segs = _jload(proj / "segments.json", [])
    return {s["id"]: (s["frame"] / 30.0, (s["frame"] + s["frames"]) / 30.0) for s in segs if "frame" in s}


def context(proj: Path) -> dict:
    edl = _jload(proj / "edl.json", [])
    return {"pj": _jload(proj / "project.json", {}), "edl_raw": edl,
            "edl": edl if isinstance(edl, list) else edl.get("segments", []),
            "wins": _windows(proj), "words": _jload(proj / "words.json", []),
            "ledger": _jload(proj / LEDGER, None), "sources": _sources(proj)}


def bad_numbers(item: dict, entries: list, sources: str) -> list:
    """Values in one on-screen string that fail the rule."""
    src_vals = set(NW.digits_in(sources)) if item.get("hero") == "evidence-hero" and \
        item["field"] in SOURCE_FIELDS | {"steps", "values"} else set()
    return [v for v in NW.digits_in(item["text"]) if v not in src_vals and not _ok_value(v, item["scope"], entries)]


def caption_bad(words: list, entries: list) -> list:
    out = []
    for w in words:
        for v in NW.digits_in(w.get("text", "")):
            t = float(w["start"])
            hit = any(e["status"] in OK_STATUS and NW.same(e["value"], v) and abs(e["t0"] - t) <= CAPTION_TOL
                      for e in entries if e["src"] == "caption")
            if not hit:
                out.append({"where": f"captions@{t:.2f}", "text": w["text"], "values": [v]})
    return out


def unverified(proj: Path, ctx: dict | None = None) -> list:
    """Every on-screen number that is not verified, confirmed or source-backed: [{where, text, values}]."""
    ctx = ctx or context(proj)
    entries = (ctx["ledger"] or {}).get("entries", [])
    out = caption_bad(ctx["words"], entries)
    for it in _items(proj, ctx["pj"], ctx["edl"], ctx["wins"]):
        bad = bad_numbers(it, entries, ctx["sources"])
        if bad:
            out.append({"where": it["where"], "field": it["field"], "text": it["text"], "values": bad})
    return out


def check(proj) -> dict:
    """qa.py gate numbers_verified."""
    proj = Path(proj)
    ctx = context(proj)
    if ctx["ledger"] is None:
        n = len(caption_bad(ctx["words"], [])) + len(_items(proj, ctx["pj"], ctx["edl"], ctx["wins"]))
        if not n:
            return {"name": "numbers_verified", "pass": True, "detail": "no numbers on screen",
                    "label": "On-screen numbers checked against the audio"}
        return {"name": "numbers_verified", "pass": False, "label": "On-screen numbers checked against the audio",
                "detail": f"{n} on-screen numbers and no ledger: run engine/numcheck.py <project> before compile"}
    bad = unverified(proj, ctx)
    st = ctx["ledger"].get("stats", {})
    detail = (f"{st.get('verified', 0)} verified, {st.get('confirmed', 0)} confirmed, {st.get('blocked', 0)} blocked "
              f"(work/number_flags.json); on screen unverified: {len(bad)}")
    if bad:
        detail += ". " + "; ".join(f"{b['where']}: {b['text']!r} ({', '.join(b['values'])})" for b in bad[:6])
    return {"name": "numbers_verified", "pass": not bad, "detail": detail,
            "label": "On-screen numbers checked against the audio"}


# ---------------------------------------------------------------------------------------------- compile-time scrub
def _fails(text, scope, entries, sources, hero=None, field="text") -> list:
    return bad_numbers({"text": str(text), "scope": scope, "hero": hero, "field": field}, entries, sources)


def _strip_part(part: str) -> str | None:
    """Words-only version of a headline line (None when nothing readable is left)."""
    italic = part.startswith("_") and part.endswith("_") and len(part) > 2
    txt = NW.strip_numbers(part.strip("_"))
    if not any(ch.isalpha() for ch in txt):
        return None
    return f"_{txt}_" if italic else txt


def scrub_headline(text: str, bad) -> str | None:
    """'MAIN|_sub_': an italic sub-line with a bad number is dropped, a main line keeps its words."""
    parts = []
    for p in str(text).split("|"):
        if not bad(p):
            parts.append(p)
        elif not p.startswith("_"):
            s = _strip_part(p)
            if s:
                parts.append(s)
    return "|".join(parts) or None


def _args_of(card: dict) -> dict:
    return card.get("args") if isinstance(card.get("args"), dict) else card


def scrub_card(card: dict, bad) -> dict | None:
    """A card / insert with its unverified numbers removed (words-only), or None (the graphic is dropped)."""
    card = json.loads(json.dumps(card))
    args = _args_of(card)
    for k in list(args):
        v = args[k]
        if k in SKIP_KEYS or not any(bad(t) for _, t in onscreen_strings(v, k)):
            continue
        if k in OPTIONAL:
            del args[k]
        elif k == "steps":
            args[k] = [s for s in v if not bad(str(s[0]))]
            if not args[k]:
                return None
        elif k == "items" and isinstance(v, list):
            args[k] = [x for x in v if not bad(str(x))]
            if len(args[k]) < 2:
                return None
        elif k == "value":                      # a number card: its context line, words-only
            ctx = args.pop("context", None)
            if not ctx or bad(ctx) or not any(ch.isalpha() for ch in ctx):
                return None
            args.pop("value")
            args["text"] = ctx
            if card.get("comp") == "ed-number":
                card["comp"] = "ed-headline"
            elif args.get("comp") == "ed-number":
                args["comp"] = "ed-headline"
        elif isinstance(v, str):
            s = NW.strip_numbers(v)
            if not any(ch.isalpha() for ch in s):
                return None
            args[k] = s
        else:
            return None
    return card if not any(bad(t) for _, t in onscreen_strings(card)) else None


def _reason(entries: list, values: list) -> str:
    e = next((e for e in entries if e["status"] == "blocked" and e["value"] in values), None)
    return e["reason"] if e else "not in the numbers ledger"


def _scrub_editorial(pj: dict, wins: dict, entries: list, sources: str, notes: list) -> None:
    for sid, b in ((pj.get("editorial") or {}).get("beats") or {}).items():
        w, had = wins.get(sid), bool(b.get("headlines"))
        heads = []
        for h in b.get("headlines") or []:
            bad = (lambda t, w=w: _fails(t, w, entries, sources))
            vals = bad(h.get("text", ""))
            if not vals:
                heads.append(h)
                continue
            new = scrub_headline(h["text"], bad)
            notes.append(f"beat {sid}: number {', '.join(vals)} not verified ({_reason(entries, vals)}): headline "
                         + (f"shown words-only {new!r}" if new else "dropped"))
            if new:
                heads.append({**h, "text": new})
        if "headlines" in b:
            b["headlines"] = heads
        if b.get("scene") == "set" and had and not heads:
            b["scene"], b["cards"] = "room", b.get("cards", [])
            notes.append(f"beat {sid}: no headline left, back to the room")
        b["cards"] = _scrub_cards(b.get("cards") or [], sid, w, wins, entries, sources, notes)


def _scrub_cards(cards: list, sid: str, w, wins: dict, entries: list, sources: str, notes: list) -> list:
    out = []
    for c in cards:
        end = wins.get(c.get("end_seg"), w) if w else None
        scope = (w[0], end[1]) if w and end else w
        hero = c.get("comp") if c.get("kind") == "hero" else (c.get("args") or {}).get("comp")

        def bad(t, scope=scope, hero=hero):
            return _fails(t, scope, entries, sources, hero, "text")
        vals = sorted({v for _, t in onscreen_strings(c) for v in bad(t)})
        if not vals:
            out.append(c)
            continue
        new = scrub_card(c, bad)
        name = c.get("comp") or (c.get("args") or {}).get("comp") or c.get("insert") or c.get("kind")
        notes.append(f"beat {sid}: number {', '.join(vals)} not verified ({_reason(entries, vals)}): {name} "
                     + ("shown words-only" if new else "dropped"))
        if new:
            out.append(new)
    return out


def _scrub_edl(edl: list, wins: dict, entries: list, sources: str, notes: list) -> None:
    for row in edl:
        top = row.get("top")
        if not top:
            continue
        items = top if isinstance(top, list) else [top]
        kept = _scrub_cards(items, row.get("id"), wins.get(row.get("id")), wins, entries, sources, notes)
        if kept == items:
            continue
        if not [k for k in kept if (k.get("insert") if isinstance(k, dict) else None) != "ground"]:
            row["top"], row["mode"] = None, "full"
        else:
            row["top"] = kept if isinstance(top, list) else kept[0]


def scrub(proj, notes: list | None = None) -> list:
    """Compile time: remove every unverified on-screen number from project.json / edl.json (words-only or the graphic
    dropped). Returns the compile notes. Never touches words.json (numcheck.py did the captions)."""
    from compile.common import jwrite
    proj, notes = Path(proj), notes if notes is not None else []
    ctx = context(proj)
    entries = (ctx["ledger"] or {}).get("entries", [])
    pj, edl, wins, src = ctx["pj"], ctx["edl"], ctx["wins"], ctx["sources"]
    n0 = len(notes)
    hook = pj.get("hook") or {}
    for k in ("l1", "l2"):
        vals = _fails(hook.get(k, ""), None, entries, src)
        if vals:
            hook[k] = NW.strip_numbers(hook[k])
            notes.append(f"hook {k}: number {', '.join(vals)} not verified ({_reason(entries, vals)}): words-only")
    _scrub_editorial(pj, wins, entries, src, notes)
    _scrub_edl(edl, wins, entries, src, notes)
    for b in pj.get("beats") or []:
        if b.get("items"):
            b["items"] = _scrub_cards(b["items"], b.get("seg"), wins.get(b.get("seg")), wins, entries, src, notes)
    if len(notes) > n0:
        jwrite(proj / "project.json", pj)
        raw = ctx["edl_raw"]
        jwrite(proj / "edl.json", edl if isinstance(raw, list) else {**raw, "segments": edl})
    return notes
