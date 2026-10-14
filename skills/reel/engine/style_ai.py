"""Reel Room style scan, AI side: Gemini watches each reel and answers in strict JSON, then a second
text-only call turns the per-reel answers into a style card matched against styles/catalog.json.

Standard library only. The key goes in the x-goog-api-key header and is never printed or logged.
Key lookup: GEMINI_API_KEY in the environment, then ~/.config/watch/.env, then ~/.reel-room/.env.
Models, tried in order (REEL_SCAN_MODEL puts one first): gemini-3.7-flash, gemini-3.5-flash, gemini-3.5-flash-lite.
"""
import json
import mimetypes
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://generativelanguage.googleapis.com"
MODELS = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
KEY_FILES = ["~/.config/watch/.env", "~/.reel-room/.env"]
KEY_HELP = ("Free key: https://aistudio.google.com/apikey, then add a line GEMINI_API_KEY=<your key> to "
            "~/.reel-room/.env (or set it in your environment). Reels you scan are uploaded to Google for the "
            "analysis and deleted right after.")

# What each catalog style looks like on screen. Gemini matches against these. A style without an entry
# falls back to its catalog `desc`, so new styles work without touching this file.
SIGNALS = {
    "editorial-ui": "Speaker cut out of their room and placed on flat, solid colour backgrounds that change beat to beat; "
                    "huge display or serif words BEHIND the head; magazine-cover framing; cuts back to the real room "
                    "for UI elements like prompt bars, checklists or a countdown. Bold, premium, designed.",
    "clean-talk": "Full-frame natural talking head in a real room, very little design. Captions one or a few words at "
                  "a time near chest height; a small title at the top; at most an occasional highlighted keyword or "
                  "small card. Calm, credible, the person is the show.",
    "motion-editorial": "The top half is animated graphic design (kinetic type, a big number, charts, documents, gauges, "
                        "calendars) while the speaker sits in a rounded card or window in the lower half. Motion-design heavy.",
    "split-deck": "A hard horizontal split: the top half holds cards, B-roll, photos or screenshots, the bottom half the "
                  "speaker; short captions sit on the seam between them; hook card, checklists that tick, teaching tone.",
    "list-stack": "A numbered list ('5 things') that builds item by item above the speaker's head and stays on screen; "
                  "the current item lights up; the numbers never move.",
    "floating-cards": "Speaker full frame (often cut out) with small frosted or glass cards popping in around them on "
                      "key words, plus one big word behind the head; bright and warm; one caption word at a time.",
    "carousel-slideup": "Cream or paper cards, one per point, slide up over the lower half of the frame on each cut like "
                        "swiping a carousel; a static title on top; usually no running captions.",
    "desk-demo": "Cuts away from the speaker to screen recordings or a phone-filmed computer or phone screen (apps, "
                 "dashboards, websites, portals) with a cursor clicking or highlights; hands-on tutorial feel.",
}

REEL_PROMPT = """You are a senior short-form video editor. Watch this vertical reel closely and describe HOW it is edited
(not what it is about). Answer with ONE JSON object, no prose, exactly these keys:
{
 "layout": {"type": one of ["full-frame talking head","split top/bottom","speaker in a card or window","speaker cut out on a designed background","screen or app recording","faceless graphics or B-roll","mixed"], "time_share": {"full-frame speaker": percent, "split top/bottom": percent, "speaker cut out on a designed background": percent, "full-screen screen recording or graphic": percent, "other": percent}, "description": "one sentence"},
 "speaker": {"on_screen": one of ["almost always","most of the time","some of the time","rarely","never"], "framing": one of ["close-up","medium","wide","none"], "cut_out_of_background": true/false, "text_behind_head": true/false},
 "captions": {"present": true/false, "style": "font, weight, colour, box or pill, outline, animation", "words_per_chunk": integer or null, "position": one of ["top","upper third","middle","chest height","lower third","bottom","on a split seam","none"], "case": one of ["ALL CAPS","Sentence case","lowercase","mixed","none"], "highlight": "how key words are emphasised, or none"},
 "title_hook": {"present": true/false, "treatment": "what the opening title looks like", "position": "where", "stays_on_screen": true/false},
 "graphics": {"amount": one of ["none","light","medium","heavy"], "types": ["short labels like screenshot, chart, number card, checklist, emoji, sticker, photo, B-roll clip, icon, arrow, map, document"], "description": "one sentence"},
 "list_structure": "does it count through numbered points on screen? how is the list shown? or none",
 "screen_content": "any screen recordings or filmed screens and how they are shown, or none",
 "color_grade": {"background": "what is behind the speaker or under the graphics", "palette": ["3 to 5 colour words"], "grade": "warm, cool, neutral, high contrast, dark, bright..."},
 "pacing": {"feel": one of ["slow","medium","fast"], "avg_shot_seconds": number, "punch_in_zooms": true/false, "transitions": "hard cuts, whips, slides..."},
 "sound": {"music": "none, or the kind of music and how loud", "sfx": "none, or what kind and when", "voice": "talking to camera, voice-over, none"},
 "signature_moves": ["2 to 5 specific, repeatable editing moves that make this reel recognisable"],
 "summary": "two plain sentences a non-editor understands"
}
Only describe what you actually see and hear. If something is absent, say none or false."""

MATCH_PROMPT = """You are a senior short-form video editor. Below are structured notes about {n} reels {who}, plus a few
measured numbers. Build a style card {goal}.

Reel notes (JSON list):
{reels}

Measured numbers (from pixels, rough): {numbers}

Our style catalog. You may ONLY recommend these ids:
{catalog}

Answer with ONE JSON object, no prose, exactly these keys:
{{
 "summary": "2 plain sentences describing the look, {voice}, no jargon",
 "system": [{{"label": one of ["Layout","Captions","Title","Graphics","Color","Pacing","Sound","Signature"], "text": "one plain sentence about what repeats, same voice as summary"}}],
 "consistent": ["things that stay the same across the reels (the system)"],
 "varies": ["things that change from reel to reel"],
 "matches": [{{"id": "catalog id", "fit": 0-100, "reason": "one plain sentence that names what was SEEN in the reels and the catalog trait it matches, e.g. their captions sit in a dark pill at chest height and they cut to full-screen screenshots, which is Desk demo"}}],
 "confidence": one of ["high","medium","low"],
 "no_fit": "if no catalog style is a real match (best fit under 55), one plain sentence saying what is missing; otherwise null"
}}
Rules: exactly 3 matches, best first, 3 different ids from the catalog. Rank by the BACKBONE of the edit: first the
layout that fills most of the screen time across most reels (use layout.time_share), then how captions look and sit,
then the kind of graphics. A move seen in only one reel, or for a few seconds, is a detail: list it under "varies" and
do not let it decide the top pick. Recurring numbered lists on screen point to List stack; small cards popping around a
full-frame speaker point to Floating cards; one or two caption words at chest height over a natural room point to Clean Talk. Fit is how close the catalog style is to what
you saw, be honest (a weak match is 30, not 70). Use the creator's real moves in the reasons. No em dashes."""


def log(msg):
    import sys
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- key
def _read_env(path):
    out = {}
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)\s*$", line)
                if m:
                    out[m.group(1)] = m.group(2).strip().strip("'\"")
    except OSError:
        pass
    return out


def load_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    for p in KEY_FILES:
        if k:
            break
        k = _read_env(p).get("GEMINI_API_KEY", "").strip()
    return k or None


# ---------------------------------------------------------------- http
class GeminiError(Exception):
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind            # auth, busy, rejected, network, response


def _call(method, url, key, data=None, headers=None, timeout=120):
    req = Request(url, data=data, method=method, headers={"x-goog-api-key": key, **(headers or {})})
    try:
        with urlopen(req, timeout=timeout) as r:
            return dict(r.headers), r.read()
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            msg = body[:200]
        msg = msg.replace(key, "[key]")
        kind = ("auth" if e.code in (401, 403) or "api key" in msg.lower() else
                "busy" if e.code in (429, 500, 502, 503, 504) else "rejected")
        raise GeminiError(kind, f"HTTP {e.code}: {msg[:200]}") from None
    except (URLError, TimeoutError, OSError) as e:
        raise GeminiError("network", f"{type(e).__name__}: {getattr(e, 'reason', e)}") from None


def upload(path, key, max_wait=300):
    size = os.path.getsize(path)
    mime = mimetypes.guess_type(path)[0] or "video/mp4"
    hdr, _ = _call("POST", f"{API}/upload/v1beta/files", key,
                   data=json.dumps({"file": {"display_name": "reel-room-style-scan"}}).encode(),
                   headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                            "X-Goog-Upload-Header-Content-Length": str(size),
                            "X-Goog-Upload-Header-Content-Type": mime, "Content-Type": "application/json"})
    sess = {k.lower(): v for k, v in hdr.items()}.get("x-goog-upload-url")
    if not sess:
        raise GeminiError("response", "no upload session")
    with open(path, "rb") as f:
        _, body = _call("POST", sess, key, data=f, timeout=1800,
                        headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                                 "X-Goog-Upload-Command": "upload, finalize"})
    info = json.loads(body)["file"]
    t0 = time.time()
    while info.get("state") == "PROCESSING":
        if time.time() - t0 > max_wait:
            delete(info["name"], key)
            raise GeminiError("busy", "Google took too long to process the video")
        time.sleep(2)
        info = json.loads(_call("GET", f"{API}/v1beta/{info['name']}", key)[1])
    if info.get("state") != "ACTIVE":
        delete(info["name"], key)
        raise GeminiError("rejected", f"video state {info.get('state')}")
    return {"name": info["name"], "uri": info["uri"], "mime": info.get("mimeType") or mime}


def delete(name, key):
    try:
        _call("DELETE", f"{API}/v1beta/{name}", key, timeout=30)
    except GeminiError:
        pass                        # files expire on their own after 48 h


def models():
    first = os.environ.get("REEL_SCAN_MODEL", "").strip()
    return ([first] if first else []) + [m for m in MODELS if m != first]


def generate(key, parts, temperature=0.2):
    """Ask the first model that answers. Busy (429/503) waits and retries, then moves to the next model.
    Returns (parsed_json, model, tokens)."""
    body = json.dumps({"contents": [{"role": "user", "parts": parts}],
                       "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}).encode()
    last = None
    for model in models():
        for attempt in range(3):
            try:
                _, raw = _call("POST", f"{API}/v1beta/models/{model}:generateContent", key, data=body,
                               headers={"Content-Type": "application/json"}, timeout=300)
                d = json.loads(raw)
                text = "".join(p.get("text", "") for c in d.get("candidates", [])[:1]
                               for p in c.get("content", {}).get("parts", []) if not p.get("thought"))
                tokens = (d.get("usageMetadata") or {}).get("totalTokenCount")
                return parse_json(text), model, tokens
            except GeminiError as e:
                last = e
                if e.kind == "auth":
                    raise
                if e.kind == "busy" and attempt < 2 and "quota" not in str(e).lower():
                    wait = 4 * (attempt + 1)
                    log(f"  Google is busy ({model}), trying again in {wait} s")
                    time.sleep(wait)
                    continue
                break               # rejected / network / bad answer: next model
            except (ValueError, KeyError, TypeError) as e:
                last = GeminiError("response", f"unreadable answer: {e}")
                break
        log(f"  {model} did not answer ({last}), trying the next model")
    raise last or GeminiError("response", "no model answered")


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


# ---------------------------------------------------------------- per reel + match
def watch_reel(path, key):
    """Upload one reel, get the editor's JSON, delete the upload. Returns (json, model, tokens)."""
    f = upload(path, key)
    try:
        return generate(key, [{"file_data": {"mime_type": f["mime"], "file_uri": f["uri"]}}, {"text": REEL_PROMPT}])
    finally:
        delete(f["name"], key)


def watch_all(paths, key, workers=3):
    """Run watch_reel over the files, 3 at a time. Returns list of (path, json|None, model, tokens, error)."""
    def one(p):
        try:
            j, m, t = watch_reel(p, key)
            log(f"  watched {os.path.basename(p)} ({m})")
            return p, j, m, t, None
        except GeminiError as e:
            log(f"  could not watch {os.path.basename(p)}: {e}")
            return p, None, None, None, e
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, paths))


def catalog_text(catalog):
    return "\n".join(f'- {s["id"]} ({s["name"]}): {SIGNALS.get(s["id"], s.get("desc", ""))}'
                     for s in catalog if not s.get("coming"))


def match(reels, numbers, catalog, key, mode):
    who = "by one creator the user wants to model" if mode == "creator" else "from the user's own account"
    goal = ("that explains the repeatable system behind this creator's edits" if mode == "creator"
            else "that describes the user's current look so we can suggest styles that fit it")
    voice = ("about this creator in the third person (they, their)" if mode == "creator"
             else "speaking to the user about their own reels (you, your)")
    prompt = MATCH_PROMPT.format(n=len(reels), who=who, goal=goal, voice=voice, reels=json.dumps(reels, ensure_ascii=False),
                                 numbers=json.dumps(numbers), catalog=catalog_text(catalog))
    return generate(key, [{"text": prompt}], temperature=0.1)


def clean_matches(raw, catalog):
    """Keep only real catalog ids, no repeats, fit clamped 0..100, best first. Never more than 3."""
    ids = {s["id"] for s in catalog if not s.get("coming")}
    out, seen = [], set()
    for m in raw if isinstance(raw, list) else []:
        sid = str((m or {}).get("id", "")).strip()
        if sid in ids and sid not in seen:
            seen.add(sid)
            try:
                fit = max(0, min(100, int(float(m.get("fit", 0)))))
            except (TypeError, ValueError):
                fit = 0
            out.append({"id": sid, "fit": fit, "reason": no_dash(str(m.get("reason", "")).strip())})
    return sorted(out, key=lambda x: -x["fit"])[:3]


def no_dash(s):
    return re.sub("\\s*[\u2014\u2013]\\s*", ", ", s or "")
