"""Hero beats (plan component "custom"): a library hero when one fits (hero_lib.py: a fast model picks a hero from the
catalogue and fills its typed contract, hero_schema.py validates it), else a strong kit fallback; the bespoke idea is
queued for a Claude pass either way.

The fallback is chosen by llm_router.typed from the hero's idea + line, limited to the components the style can show,
and validated like any planner beat (on-screen words come from the line, the anchor is in the line). No key, no
network or a failed call -> an offline pick (the anchor word as a big label). Choices are cached in work/hero_todo.json
per (line, idea, style), so a re-compile never pays twice and never blocks the render.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import llm_router as LR
import plan_schema as PS

from . import hero_lib as HL
from .common import jload, jwrite

TODO = "work/hero_todo.json"
CHAIN = (LR.ROUTER, LR.FAST)
SAY = {"label-pill": "one big word or short phrase on a card", "checklist-tick": "2-3 items that tick on their words",
       "odometer": "a number that rolls up and lands", "typer": "words typed into a prompt bar",
       "before-after": "'A -> B' before and after", "comment-cta": "a comment field typing a keyword",
       "stepper": "2-4 steps that light up", "phone-frame": "the speaker shrinks into a phone screen",
       "progress-bar": "a bar that fills to a number"}


def hero_prompt(beat: dict, allowed: list, context: str) -> str:
    menu = "\n".join(f"- {c}: {SAY.get(c, c)}" for c in allowed)
    return f"""A reel needs a strong stand-in graphic for a planned bespoke hero moment (the bespoke one comes later).
Hero idea: {beat['visual_intent']}
THIS LINE: {beat['line']}
Neighbouring lines: {context}

Pick the closest graphic:
{menu}
On-screen text uses ONLY words and numbers spoken in THIS LINE (copy them exactly), max {PS.MAX_TEXT} chars, never
empty, no em dash. anchor_word: one word copied from THIS LINE where the graphic lands (prefer {beat['anchor_word']!r}).
JSON only: {{"component": one of {allowed}, "on_screen_text": "...", "anchor_word": "...", "why": "max 12 words"}}"""


def validator(line: str, context: str, allowed: list):
    base = PS.check_beat(line, context)

    def check(d: dict) -> str | None:
        if d.get("component") not in allowed:
            return f"component must be one of {allowed}"
        if not str(d.get("on_screen_text", "")).strip():
            return "on_screen_text must not be empty for a hero"
        return base(d)
    return check


def offline_pick(beat: dict) -> dict:
    """The anchor word, as spoken, on a big card: always valid, always readable."""
    word = next((w for w in beat["line"].split() if w.strip(".,!?;:'\"").lower() ==
                 str(beat["anchor_word"]).strip(".,!?;:'\"").lower()), beat["anchor_word"])
    word = word.strip(".,!?;:\"")
    return {"component": "label-pill", "on_screen_text": word, "anchor_word": word, "source": "offline"}


def _cached(todo: list, beat: dict, style: str, use_llm: bool):
    """A cached choice for the same line, idea and style. An offline pick is not reused when a model call is allowed."""
    for t in todo:
        if t.get("line_id") == beat["id"] and t.get("idea") == beat["visual_intent"] and t.get("style") == style:
            fb = t.get("fallback") or {}
            if fb.get("component") and (fb.get("source") == "llm" or not use_llm):
                return fb
    return None


def _ask(beat: dict, allowed: list, context: str) -> dict:
    try:
        res = LR.typed(hero_prompt(beat, allowed, context), validator(beat["line"], context, allowed), CHAIN, 600)
    except LR.LLMError as exc:
        return {**offline_pick(beat), "note": str(exc)}
    if res["data"] is None:
        return {**offline_pick(beat), "note": res["attempts"][-1]["error"]}
    d = res["data"]
    return {"component": d["component"], "on_screen_text": d["on_screen_text"].strip(),
            "anchor_word": d["anchor_word"], "why": d.get("why", ""), "source": "llm",
            "cost": round(sum(a["cost"] or 0 for a in res["attempts"]), 5)}


def _cached_lib(todo: list, beat: dict, style: str):
    for t in todo:
        if t.get("line_id") == beat["id"] and t.get("idea") == beat["visual_intent"] and t.get("style") == style:
            lib = t.get("library") or {}
            if lib.get("source") in ("llm", "claude"):  # model pick, or a Claude-written plan (validate_plan.py)
                return lib
    return None


def _submit(pool, todo, b, style, allowed, contexts, use_llm, lib_ids, sources, secs):
    """(fallback future or value, library future or value) for one hero beat."""
    ctx = contexts.get(b["id"], "")
    fb = _cached(todo, b, style, use_llm)
    if fb is None:
        fb = pool.submit(_ask, b, allowed, ctx) if use_llm else offline_pick(b)
    lib = _cached_lib(todo, b, style)
    if lib is None:
        lib = pool.submit(HL.ask, b, lib_ids, ctx, sources, secs.get(b["id"], 2.0), b.get("library")) if use_llm \
            else {"hero": "none", "note": "offline"}
    return fb, lib


def resolve(proj, beats: list, contexts: dict, style: str, allowed: list, use_llm: bool = True,
            secs: dict | None = None) -> dict:
    """{"fallbacks": {line_id: kit fallback}, "library": {line_id: library pick}} for every hero beat; writes
    work/hero_todo.json (the queue for the Claude pass)."""
    heroes = [b for b in beats if b.get("hero")]
    todo = jload(proj / TODO, [])
    sources = HL.sources_text(proj)
    lib_ids = HL.allowed(style, sources)
    t0, out, lib = time.time(), {}, {}
    with ThreadPoolExecutor(max_workers=max(1, 2 * len(heroes))) as pool:
        jobs = {b["id"]: _submit(pool, todo, b, style, allowed, contexts, use_llm, lib_ids, sources, secs or {})
                for b in heroes}
        for lid, (fb, lp) in jobs.items():
            out[lid] = fb.result() if hasattr(fb, "result") else fb
            lib[lid] = lp.result() if hasattr(lp, "result") else lp
    rows = [{"line_id": b["id"], "line": b["line"], "anchor_word": b["anchor_word"], "idea": b["visual_intent"],
             "style": style, "status": "library" if lib[b["id"]].get("hero", "none") != "none" else "todo",
             "fallback": out[b["id"]], "library": lib[b["id"]]} for b in heroes]
    keep = [t for t in todo if (t.get("line_id"), t.get("style")) not in {(r["line_id"], style) for r in rows}]
    jwrite(proj / TODO, keep + rows)
    return {"fallbacks": out, "library": lib, "secs": round(time.time() - t0, 2)}
