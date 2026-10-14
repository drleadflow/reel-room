#!/usr/bin/env python3
"""Verify every number that can appear on screen against the audio, before compile (medical content: a misheard
number never reaches the screen).

  numcheck.py <project> [--no-llm] [--force] [--json]
  --no-llm (or no OPENROUTER key): speech only. Verified (tagged "check": "speech_only", lower confidence) only when
  reading B says exactly the caption's value on the word; any disagreement or a missing number is still blocked.

For each number in the captions (words.json) and in the EDL lines (everything a card, hero or headline may quote):
  1. reading A = the caption / line as built (medium.en full pass + the EDL line)
  2. reading B = a fresh medium.en pass over a small window around the word with a numbers-focused prompt
     (splice.transcribe_window, the engine's own transcribe path)
  3. a cheap text model compares both readings and the spoken line in context (llm_router.typed, typed verdict
     {agree: bool, value, confidence})
Verified = reading B says the same value AND the model agrees on that value with confidence >= MIN_CONF.
Anything else is BLOCKED: a blocked caption number is removed from words.json (backup work/words.prenum.json), the
compiler shows blocked numbers words-only or drops the graphic (numgate.py), and the number goes to
work/number_flags.json for a human. Confirm one by hand in project.json:
  "numbers_ok": [{"value": "7", "t": 33.1, "why": "listened: over seven"}]       (t or seg optional)
Writes work/numbers.json (the ledger the compile gate and qa.py "numbers_verified" read). Exit 0 when it ran.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import numwords as NW  # noqa: E402

LEDGER, FLAGS, CACHE = "work/numbers.json", "work/number_flags.json", "work/numcheck_cache.json"
PAD = 1.6               # s of audio either side of the number for reading B
NEAR = 0.8              # s around the word where reading B must say the value
AT = 0.3                # s: speech-only mode (no model) needs reading B to say the value right on the word
GROUP_GAP = 3.0         # numbers closer than this share one re-transcription window
MAX_WIN = 12.0
MIN_CONF = 0.8
MODEL = "medium.en"
NUM_PROMPT = ("Numbers are written as digits, for example: over 7, 0.24, 8 weeks, 12 weeks, 16 weeks, 30%, "
              "$60 billion, 2023.")


# ---------------------------------------------------------------------------------------------- candidates
def seg_of(t: float, wins: dict) -> str | None:
    return next((sid for sid, (a, b) in wins.items() if a - 0.05 <= t < b), None)


def caption_candidates(words: list, wins: dict) -> list:
    out = []
    for i, w in enumerate(words):
        for v in NW.digits_in(w.get("text", "")):
            t0, t1 = float(w["start"]), float(w["end"])
            out.append({"src": "caption", "word_i": i, "shown": w["text"], "value": v, "t0": round(t0, 3),
                        "t1": round(t1, 3), "seg": seg_of((t0 + t1) / 2, wins)})
    return out


def line_candidates(lines: dict, wins: dict, caps: list) -> list:
    """Numbers in an EDL line that no caption token in that segment shows (cards can still quote them)."""
    out = []
    for sid, line in lines.items():
        if sid not in wins:
            continue
        shown = {c["value"] for c in caps if c["seg"] == sid}
        for v in NW.digits_in(line):
            if v not in shown:
                a, b = wins[sid]
                out.append({"src": "line", "shown": line, "value": v, "t0": round(a, 3),
                            "t1": round(min(b, a + MAX_WIN - 2 * PAD), 3), "seg": sid})
    return out


def candidates(proj: Path) -> tuple:
    """(candidates, lines, wins) for the project."""
    from compile.common import edl_list, jload, windows
    from compile.validate import edl_lines
    wins = windows(jload(proj / "segments.json"))
    lines = edl_lines(edl_list(jload(proj / "edl.json")))
    caps = caption_candidates(jload(proj / "words.json"), wins)
    cands = caps + line_candidates(lines, wins, caps)
    for i, c in enumerate(sorted(cands, key=lambda c: c["t0"])):
        c["id"] = f"n{i:02d}"
    return sorted(cands, key=lambda c: c["t0"]), lines, wins


def groups(cands: list, dur: float) -> list:
    """[(a, b, [candidates])]: one re-transcription window per run of nearby numbers."""
    out = []
    for c in sorted(cands, key=lambda c: c["t0"]):
        a, b = round(max(0.0, c["t0"] - PAD), 3), round(min(dur, c["t1"] + PAD), 3)
        last = out[-1] if out else None
        if last and c["t0"] - max(x["t1"] for x in last[2]) <= GROUP_GAP and b - last[0] <= MAX_WIN:
            out[-1] = (last[0], max(last[1], b), last[2] + [c])
        else:
            out.append((a, b, [c]))
    return out


# ---------------------------------------------------------------------------------------------- reading B
def whisper_transcriber(proj: Path):
    """(audio seconds, fn(a, b) -> [{w, s, e, p}]) over the final cut audio, medium.en, numbers prompt."""
    import numpy as np
    import common as C
    import words as WD
    from splice import read_wav, transcribe_window
    wav = WD.final_wav(proj)
    audio = (read_wav(wav)[0] / 32768.0).astype(np.float32)
    prompt = " ".join(x for x in (C.names_prompt(proj), NUM_PROMPT) if x)
    model = C.whisper_model(MODEL)
    return len(audio) / 16000.0, lambda a, b: transcribe_window(model, audio, a, b, prompt), C.content_hash(wav)


def reading_b(win_words: list, c: dict) -> dict:
    near = [w for w in win_words if w["e"] >= c["t0"] - NEAR and w["s"] <= c["t1"] + NEAR]
    text_near = " ".join(w["w"] for w in near)
    at = [w for w in win_words if w["e"] >= c["t0"] - AT and w["s"] <= c["t1"] + AT]    # right on the word
    return {"near": text_near, "window": " ".join(w["w"] for w in win_words),
            "values": sorted(NW.spoken_values(text_near)), "at": sorted(NW.spoken_values(" ".join(w["w"] for w in at)))}


# ---------------------------------------------------------------------------------------------- verdict
def verdict_prompt(c: dict, b: dict, ctx: str) -> str:
    return f"""You check numbers before they appear on screen in a medical short video. Two independent
speech-to-text readings of the same spoken moment are below. Decide whether the number that will be shown is
really what was said.

Number that will be shown: {c['value']}   (as built: {c['shown']!r})
Reading A (captions / script line): {ctx}
Reading B (fresh re-transcription of the audio around the word): {b['window']!r}
Reading B right at the word: {b['near']!r}

Agree only when reading B says the same number as reading A at that moment (digits or words, '7' = 'seven',
'0.24' = 'point two four') and the number makes sense in the sentence. If reading B says a different number, says
no number there, or it is unclear, agree is false. value = the number you believe was said, as digits.
JSON only: {{"agree": true or false, "value": "digits", "confidence": 0.0 to 1.0}}"""


def check_verdict(c: dict):
    """llm_router.typed validator for {agree, value, confidence}."""
    def check(d: dict) -> str | None:
        if not isinstance(d.get("agree"), bool):
            return "agree must be true or false"
        conf = d.get("confidence")
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            return "confidence must be a number from 0 to 1"
        if NW.canon(d.get("value")) is None:
            return "value must be the number as digits"
        if d["agree"] and not NW.same(d["value"], c["value"]):
            return f"agree is true but value {d['value']!r} is not {c['value']}"
        return None
    return check


def llm_judge(c: dict, b: dict, ctx: str) -> dict:
    """{agree, value, confidence, cost} or {"error"}; never raises."""
    import llm_router as LR
    try:
        res = LR.typed(verdict_prompt(c, b, ctx), check_verdict(c), (LR.FAST, LR.ROUTER), 300)
    except LR.LLMError as exc:
        return {"error": str(exc)}
    cost = round(sum(a["cost"] or 0 for a in res["attempts"]), 5)
    if res["data"] is None:
        return {"error": res["attempts"][-1]["error"], "cost": cost}
    d = res["data"]
    return {"agree": d["agree"], "value": NW.canon(d["value"]), "confidence": float(d["confidence"]), "cost": cost}


def speech_judge(c: dict, b: dict, ctx: str) -> dict:
    """No key / --no-llm: no model verdict; decide() then needs the two transcripts to agree right on the word."""
    return {"speech_only": True}


def decide(c: dict, b: dict, v: dict) -> tuple:
    """(status, reason). verified only when both readings and the model agree with enough confidence; without a
    model (speech_only) only when reading B says exactly that value on the word (a lower-confidence verified)."""
    if v.get("speech_only"):
        if c["value"] in b.get("at", []):
            return "verified", "speech only: both transcripts say it on the word (no model check, lower confidence)"
        heard = ", ".join(b.get("at") or []) or "no number"
        return "blocked", f"speech only: reading B heard {heard} on the word ({b['near']!r})"
    if c["value"] not in b["values"]:
        heard = ", ".join(b["values"]) or "no number"
        return "blocked", f"readings disagree: reading B heard {heard} ({b['near']!r})"
    if "error" in v:
        return "blocked", f"no model verdict ({v['error'][:80]})"
    if not v["agree"] or not NW.same(v["value"], c["value"]):
        return "blocked", f"model disagrees: believes {v.get('value')} was said"
    if v["confidence"] < MIN_CONF:
        return "blocked", f"low confidence {v['confidence']:.2f} < {MIN_CONF}"
    return "verified", "both readings and the model agree"


# ---------------------------------------------------------------------------------------------- confirmations
def confirmed(c: dict, oks: list) -> dict | None:
    """A human confirmation from project.json "numbers_ok" that matches this number (value, and t or seg if given)."""
    for ok in oks or []:
        if not NW.same(ok.get("value"), c["value"]):
            continue
        if "t" in ok and not c["t0"] - 1.0 <= float(ok["t"]) <= c["t1"] + 1.0:
            continue
        if "seg" in ok and ok["seg"] != c["seg"]:
            continue
        return ok
    return None


def context_of(c: dict, lines: dict) -> str:
    ids = list(lines)
    if c["seg"] not in lines:
        return c["shown"]
    i = ids.index(c["seg"])
    return " ".join(lines[j] for j in ids[max(0, i - 1):i + 2])


# ---------------------------------------------------------------------------------------------- run
def _cache_key(*parts) -> str:
    return hashlib.blake2b(json.dumps(parts, sort_keys=True).encode(), digest_size=8).hexdigest()


def _readings(cands: list, dur: float, transcribe, cache: dict, akey: str) -> dict:
    """{candidate id: reading B}; one re-transcription per window group, cached by audio + window."""
    out = {}
    for a, b, cs in groups(cands, dur):
        k = _cache_key("tx", akey, a, b, NUM_PROMPT, MODEL)
        if k not in cache:
            cache[k] = transcribe(a, b)
        for c in cs:
            out[c["id"]] = {**reading_b(cache[k], c), "win": [a, b]}
    return out


def _verdicts(cands: list, reads: dict, lines: dict, judge, cache: dict) -> dict:
    todo, out = {}, {}
    for c in cands:
        ctx = context_of(c, lines)
        k = _cache_key("v", getattr(judge, "__name__", "j"), c["value"], c["shown"], reads[c["id"]]["window"], ctx)
        if k in cache and "error" not in cache[k]:
            out[c["id"]] = cache[k]
        else:
            todo[c["id"]] = (k, c, ctx)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {cid: (k, pool.submit(judge, c, reads[cid], ctx)) for cid, (k, c, ctx) in todo.items()}
        for cid, (k, f) in futs.items():
            out[cid] = cache[k] = f.result()
    return out


def verify(proj: Path, transcribe=None, judge=None, dur: float | None = None, akey: str = "",
           use_llm: bool = True) -> dict:
    """The ledger {entries, stats}. transcribe(a, b) -> [{w, s, e, p}] and judge(c, b, ctx) -> verdict are injectable
    (tests); defaults are medium.en and the cheap model chain."""
    t0 = time.time()
    cands, lines, wins = candidates(proj)
    if transcribe is None and cands:
        dur, transcribe, akey = whisper_transcriber(proj)
    cache = json.loads((proj / CACHE).read_text()) if (proj / CACHE).exists() else {}
    reads = _readings(cands, dur or max((b for _, b in wins.values()), default=0.0), transcribe, cache, akey)
    judge = judge or (llm_judge if use_llm else speech_judge)
    verdicts = _verdicts(cands, reads, lines, judge, cache) if cands else {}
    pj = json.loads((proj / "project.json").read_text()) if (proj / "project.json").exists() else {}
    entries = []
    for c in cands:
        status, why = decide(c, reads[c["id"]], verdicts[c["id"]])
        ok = confirmed(c, pj.get("numbers_ok"))
        if status == "blocked" and ok:
            status, why = "confirmed", f"confirmed by hand: {ok.get('why', '')}"
        check = "speech_only" if verdicts[c["id"]].get("speech_only") else "model"
        entries.append({**c, "reading_b": reads[c["id"]], "verdict": verdicts[c["id"]], "status": status,
                        "check": check if status == "verified" else ("human" if status == "confirmed" else check),
                        "reason": why})
    (proj / CACHE).write_text(json.dumps(cache))
    return {"entries": entries, "audio": akey, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stats": {"numbers": len(entries), "verified": sum(e["status"] == "verified" for e in entries),
                      "confirmed": sum(e["status"] == "confirmed" for e in entries),
                      "blocked": sum(e["status"] == "blocked" for e in entries), "secs": round(time.time() - t0, 1),
                      "speech_only": sum(e.get("check") == "speech_only" and e["status"] == "verified"
                                         for e in entries), "mode": "model" if use_llm else "speech_only",
                      "cost_usd": round(sum((e["verdict"] or {}).get("cost") or 0 for e in entries), 5)}}


def block_captions(proj: Path, ledger: dict) -> list:
    """Remove blocked caption numbers from words.json (backup once in work/words.prenum.json). Returns removed."""
    blocked = [e for e in ledger["entries"] if e["status"] == "blocked" and e["src"] == "caption"]
    if not blocked:
        return []
    wpath = proj / "words.json"
    words = json.loads(wpath.read_text())
    bak = proj / "work" / "words.prenum.json"
    if not bak.exists():
        bak.write_text(json.dumps(words))
    drop = set()
    for e in blocked:
        i = e.get("word_i")
        if i is not None and i < len(words) and NW.digits_in(words[i]["text"]) and \
                abs(float(words[i]["start"]) - e["t0"]) < 0.05:
            drop.add(i)
    wpath.write_text(json.dumps([w for i, w in enumerate(words) if i not in drop], indent=1))
    return [{"t": e["t0"], "value": e["value"], "shown": e["shown"]} for e in blocked]


def flags_doc(ledger: dict) -> dict:
    rows = [{"value": e["value"], "shown": e["shown"], "seg": e["seg"], "t": e["t0"], "src": e["src"],
             "heard_b": e["reading_b"]["near"], "model": {k: e["verdict"].get(k) for k in ("agree", "value", "confidence",
                                                                                         "error")},
             "reason": e["reason"]} for e in ledger["entries"] if e["status"] == "blocked"]
    return {"flags": rows, "how_to_confirm": 'listen, then add to project.json "numbers_ok": '
            '[{"value": "<digits>", "t": <seconds>, "why": "..."}] and re-run numcheck.py'}


def has_key() -> bool:
    import llm_router as LR
    try:
        return bool(LR.api_key())
    except LR.LLMError:
        return False


def run(proj: Path, force: bool = False, use_llm: bool = True) -> dict:
    """use_llm False (or no OPENROUTER key): speech-only verification (see speech_judge)."""
    if force and (proj / CACHE).exists():
        (proj / CACHE).unlink()
    ledger = verify(proj, use_llm=use_llm and has_key())
    ledger["removed_from_captions"] = block_captions(proj, ledger)
    (proj / LEDGER).write_text(json.dumps(ledger, indent=1))
    (proj / FLAGS).write_text(json.dumps(flags_doc(ledger), indent=1))
    return ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("project")
    ap.add_argument("--force", action="store_true", help="drop the transcript / verdict cache first")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="no model verdict: verified only when both transcripts "
                    "say the value on the word (automatic without an OPENROUTER key)")
    a = ap.parse_args(argv)
    proj = Path(a.project).expanduser().resolve()
    ledger = run(proj, a.force, not a.no_llm)
    if a.json:
        print(json.dumps({"numbers": ledger["stats"], "flags": flags_doc(ledger)["flags"]}))
    else:
        for e in ledger["entries"]:
            print(f"{e['status'].upper():9} {e['value']:>8}  @{e['t0']:6.2f}  {e['seg'] or '-':6} {e['reason']}")
        print(json.dumps(ledger["stats"]))
    return 0


if __name__ == "__main__":
    import common as _C  # noqa: F401  (venv re-exec + the engine-wide CPU budget)
    _C.reexec_in_venv()
    sys.exit(main())
