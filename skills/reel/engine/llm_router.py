"""Typed LLM calls through OpenRouter, with schema validation and one-step escalation.

Every call asks for a JSON object, extracts it, runs a validator, and on any failure
(network, bad JSON, rule violation) retries on the next model in the chain. Callers get
{"data": dict | None, "attempts": [{model, secs, cost, error}]}.

Key lookup: OPENROUTER_API_KEY in the environment, then ~/.reel-room/.env.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://openrouter.ai/api/v1/chat/completions"
ROUTER = "typesafe/jev-router"          # TypeSafe Jev picks a model per request
FAST = "google/gemini-3.8-flash"        # cheap, reliable JSON fallback
STRONG = "anthropic/claude-sonnet-5.5"  # creative pass and last-resort escalation
TIMEOUT = 180
_JSON_OBJ = re.compile(r"\{.*\}", re.S)


class LLMError(RuntimeError):
    """Raised when no API key is available."""


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env = Path.home() / ".reel-room" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise LLMError("OPENROUTER_API_KEY missing: set it in the environment or ~/.reel-room/.env")


def _post(model: str, prompt: str, max_tokens: int, media=None) -> dict:
    content = [{"type": "text", "text": prompt}, *media] if media else prompt
    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"}, "usage": {"include": True},
            "max_tokens": max_tokens, "temperature": 0,
            "reasoning": {"effort": "low", "exclude": True}}
    req = Request(URL, data=json.dumps(body).encode(),
                  headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def video_part(path) -> dict:
    """An OpenRouter content part carrying a small local MP4 inline (keep it a few MB)."""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + data}}


def call_json(model: str, prompt: str, max_tokens: int = 1500, media=None) -> dict:
    """One call. Returns {routed, secs, cost, data}; raises on transport or JSON failure."""
    t0 = time.time()
    raw = _post(model, prompt, max_tokens, media)
    text = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    match = _JSON_OBJ.search(text)
    if not match:
        raise ValueError(f"no JSON object in reply ({len(text)} chars)")
    return {"routed": raw.get("model") or model, "secs": round(time.time() - t0, 2),
            "cost": (raw.get("usage") or {}).get("cost") or 0, "data": json.loads(match.group(0))}


def typed(prompt: str, validate, chain=(ROUTER, FAST, STRONG), max_tokens: int = 1500, media=None) -> dict:
    """Call each model in `chain` until one returns data that passes `validate` (returns None if ok)."""
    attempts, err = [], None
    for model in chain:
        res = {"routed": model, "secs": 0, "cost": 0}
        ask = prompt if not err else f"{prompt}\n\nYour previous answer was rejected: {err}\nReturn corrected JSON."
        try:
            res = call_json(model, ask, max_tokens, media)
            err = validate(res["data"])
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
            err = f"{type(exc).__name__}: {exc}"
        attempts.append({"model": res["routed"], "secs": res["secs"], "cost": res["cost"], "error": err})
        if not err:
            return {"data": res["data"], "attempts": attempts}
    return {"data": None, "attempts": attempts}
