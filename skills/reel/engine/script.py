"""Script directions -> suggested beats. The creator's own notes in their script drive the storyboard first.

Usage: script.py <project> [--script FILE] [--json]
Reads   P/script.md or P/script.txt (or --script FILE): the spoken script with directions in ( ) or [ ], bare links,
        and optional ==highlight== marks for the exact words a direction covers. Grammar: references/script-directives.md
Timing  words.json (cut time, after assemble) > edl.json + source words (before assemble) > edl.json lines spread evenly
Writes  P/work/directives.json {script, timing, items:[{n,t0,t1,seg,line,directive,args,raw,suggest,flag?}], flags}
        t0/t1 are seconds in CUT time (the render), null when the line is not in the cut.
Never drops a direction: anything it cannot read is kept with directive "unknown" and a plain flag.
A gif or web link is stored as a link only. Fetch it only after the user says yes.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SCRIPT_NAMES = ("script.md", "script.txt")
ASSET_DIRS = ("assets/script", "assets", "assets/broll")
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".m4v"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
TOKEN_RE = re.compile(r"==|\(([^()]*)\)|\[([^\[\]]*)\]|(https?://[^\s)\]]+)|(\n)|([^\s()\[\]=]+(?:=[^\s()\[\]=]+)*)")
SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")
NUM_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
UNTIL_RE = re.compile(r"until\s+(?:after\s+)?(?:i\s+say\s+)?[\"“']?([\w'-]+)", re.I)
# (kind, pattern on the lower-cased direction text after any leading asset number), first match wins
KINDS = [
    ("gif", re.compile(r"^gif\s*:\s*(.+)$")),
    ("broll", re.compile(r"^b[\s-]?roll\b\s*:?\s*(.*)$")),
    ("card", re.compile(r"^card\s*:\s*(.+)$")),
    ("show", re.compile(r"^show\s*:\s*(.+)$")),
    ("pop", re.compile(r"\bpop(?:s|ping)?\b")),
    ("big_text", re.compile(r"\b(?:big|bold|large)\b.*\btext\b|^big(?:,? bold)?$|^big words?$")),
    ("full", re.compile(r"\bfull[\s-]?screen\b|^full$|\bfill the (?:screen|frame)\b")),
    ("split", re.compile(r"\bsplit(?:[\s-]?screen)?\b|\bhalf[\s-]?screen\b")),
    ("list", re.compile(r"^list\b|\bas a list\b")),
    ("presenter", re.compile(r"\bpresenter\b|\bjust me\b|\bface only\b|\btalking head\b|\bno (?:graphics?|visuals?)\b")),
]
KINDS = [(k, re.compile(rx.pattern, re.I)) for k, rx in KINDS]
SUGGEST = {"full": ("full-visual", None), "big_text": (None, "big_text"), "split": ("split", None), "card": (None, "card"),
           "pop": (None, "pop_sequence"), "list": (None, "list"), "presenter": ("presenter", None), "gif": (None, "gif"),
           "broll": (None, "broll"), "show": (None, "visual"), "asset": (None, "visual")}


def norm(tok: str) -> str:
    t = C.norm(tok)
    return NUM_WORDS.get(t, t)


# ---------------------------------------------------------------------------------------------- parse
def tokenize(text: str):
    """spoken tokens [{text, hl, end}] and directions [{raw, pos, url?}] (pos = index of the next spoken token)"""
    text = re.sub(r"(\*\*|__)", "", text)
    text = "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.splitlines())
    toks, dirs, hl = [], [], False
    for m in TOKEN_RE.finditer(text):
        if m.group(0) == "==":
            hl = not hl
        elif m.group(1) is not None or m.group(2) is not None:
            dirs.append({"raw": (m.group(1) if m.group(1) is not None else m.group(2)).strip(), "pos": len(toks)})
        elif m.group(3):
            dirs.append({"raw": m.group(3), "pos": len(toks)})
        elif m.group(4):
            if toks:
                toks[-1]["end"] = True
        elif m.group(5):
            toks.append({"text": m.group(5), "hl": hl, "end": bool(SENT_END.search(m.group(5)))})
    return toks, [d for d in dirs if d["raw"]]


def anchor_span(toks, dirs, i):
    """[a, b) of the spoken tokens direction i covers: back to the previous direction or sentence start, narrowed to the
    highlighted words in that stretch. Back-to-back directions share a span. A direction with no words before it covers
    the next sentence."""
    p = dirs[i]["pos"]
    prev = dirs[i - 1]["pos"] if i else 0
    if p == prev and i:
        return dirs[i - 1]["span"]
    a = prev
    for k in range(p - 2, prev - 1, -1):
        if toks[k]["end"]:
            a = k + 1
            break
    if a >= p:                                      # nothing before it: look forward to the end of the next sentence
        b = p
        while b < len(toks) and not toks[b]["end"]:
            b += 1
        return [p, min(b + 1, len(toks))]
    hls = [k for k in range(a, p) if toks[k]["hl"]]
    return [hls[0], hls[-1] + 1] if hls else [a, p]


def parse_direction(raw: str):
    """(directive, args) for one direction text. Unknown text comes back as ('unknown', {text})."""
    s = raw.strip().strip("*").strip()
    url = re.search(r"https?://\S+", s)
    if url:
        u = url.group(0).rstrip(".,)")
        kind = "gif" if re.search(r"giphy|tenor|\.gif\b", u, re.I) else "link"
        return kind, {"url": u, "fetch": "ask first"}
    args = {}
    m = re.match(r"^(\d{1,2})(?:\s*[-:.)]\s*|\s+|$)", s)
    if m:
        args["asset"] = int(m.group(1))
        s = s[m.end():]
    body = s.strip().rstrip(".").strip()
    low = body.lower()
    for kind, rx in KINDS:
        hit = rx.search(body)
        if not hit:
            continue
        if kind in ("gif", "broll", "card", "show"):
            val = (hit.group(1) or "").strip()
            key = {"gif": "url", "broll": "desc", "card": "src", "show": "what"}[kind]
            if val:
                args[key] = val
            if kind == "card" and val.isdigit():
                args.pop("src")
                args["asset"] = int(val)
        if kind == "pop":
            args["each"] = bool(re.search(r"\beach\b|\bone by one\b", low))
            u = UNTIL_RE.search(s)
            if u:
                args["until_word"] = u.group(1)
        return kind, args
    if "asset" in args and not low:
        return "asset", args
    args["text"] = s
    return "unknown", args


# ---------------------------------------------------------------------------------------------- assets
def find_asset(proj: Path, n: int):
    rx = re.compile(rf"^0*{n}(?:[-_ .]|$)")
    for d in ASSET_DIRS:
        folder = proj / d
        if not folder.is_dir():
            continue
        hits = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in MEDIA_EXT and rx.match(f.name))
        if hits:
            return str(hits[0].relative_to(proj))
    return None


def resolve_assets(proj: Path, kind: str, args: dict):
    """adds args.src for a numbered asset; returns a flag sentence or None"""
    if "asset" in args:
        src = find_asset(proj, args["asset"])
        if src:
            args["src"] = src
            return None
        return (f"asset {args['asset']} is not in the project yet: put the file in {proj / 'assets'} named "
                f"{args['asset']}-something.png (or .jpg, .mp4)")
    if kind in ("full", "card") and not args.get("src"):
        return "which file goes here? Name it 1-something.png in the assets folder and write (1) in the script, or tell Claude"
    return None


# ---------------------------------------------------------------------------------------------- timing
def cut_time_words(proj: Path):
    """([{text,start,end}] in cut time, source label, segments)"""
    segs = C.read_json(proj / "segments.json", default=[])
    if (proj / "words.json").exists():
        return C.read_json(proj / "words.json"), "words.json", segs
    if not (proj / "edl.json").exists():
        C.fail("No words.json and no edl.json yet.", "Run ingest.py and write edl.json first (or assemble for exact times).")
    segs = segs or C.layout(C.read_json(proj / "edl.json"))
    try:
        ws = C.cut_words(proj, segs)
    except (OSError, KeyError, ValueError):
        ws = []
    if ws:
        return ws, "edl.json + source words (approximate until assemble)", segs
    out = []
    for s in segs:
        toks = (s.get("line") or "").split()
        t0, dur = s["frame"] / C.FPS, s["frames"] / C.FPS
        out += [{"text": t, "start": round(t0 + dur * k / len(toks), 3), "end": round(t0 + dur * (k + 1) / len(toks), 3)}
                for k, t in enumerate(toks)]
    return out, "edl.json lines spread evenly (rough, rerun after assemble)", segs


def token_map(toks, words):
    """script token index -> word index (exact runs, plus same-length fuzzy runs like 'five' vs '5')"""
    a, b = [norm(t["text"]) for t in toks], [norm(w["text"]) for w in words]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                if tag == "equal" or difflib.SequenceMatcher(None, a[i1 + k], b[j1 + k]).ratio() >= 0.75:
                    out[i1 + k] = j1 + k
    return out


def seg_at(segs, t):
    for s in segs:
        if s["frame"] / C.FPS <= t < (s["frame"] + s["frames"]) / C.FPS:
            return s["id"]
    return None


def place(item, span, toks, words, tmap, segs):
    a, b = span
    hit = [tmap[k] for k in range(a, b) if k in tmap]
    item["line"] = " ".join(t["text"] for t in toks[a:b])
    if not hit:
        item.update(t0=None, t1=None, seg=None)
        return "this line is not in the cut (cut out, or said differently on camera)"
    item.update(t0=round(words[min(hit)]["start"], 2), t1=round(words[max(hit)]["end"], 2))
    item["seg"] = seg_at(segs, item["t0"])
    until = item["args"].get("until_word")
    if until:
        want = norm(until)
        later = [w for w in words if item["t0"] <= w["start"] <= item["t1"] + 4 and norm(w["text"]) == want]
        if later:
            item["args"]["until_t"] = round(later[0]["end"], 2)
        else:
            return f"could not find the word '{until}' near this line to hold until"
    if len(hit) < 0.5 * (b - a):
        return f"only {len(hit)} of {b - a} words of this line were found in the cut"
    return None


# ---------------------------------------------------------------------------------------------- main
def build(proj: Path, script: Path):
    toks, dirs = tokenize(script.read_text(encoding="utf-8"))
    words, timing, segs = cut_time_words(proj)
    tmap = token_map(toks, words)
    items = []
    for i, d in enumerate(dirs):
        d["span"] = anchor_span(toks, dirs, i)
        kind, args = parse_direction(d["raw"])
        item = {"n": i + 1, "t0": None, "t1": None, "seg": None, "line": "", "directive": kind, "args": args, "raw": d["raw"]}
        flags = [place(item, d["span"], toks, words, tmap, segs), resolve_assets(proj, kind, args)]
        if kind == "unknown":
            guess = " Read it as: show " + args["text"] + "?" if len(args["text"].split()) <= 3 else ""
            flags.insert(0, f"not a direction I know, kept as written.{guess} Claude decides, you confirm")
        if kind in ("gif", "link"):
            flags.append("link saved, not downloaded. Ask the user before fetching it")
        layout, insert = SUGGEST.get(kind, (None, None))
        item["suggest"] = {"layout": layout, "insert": insert} if (layout or insert) else None
        if item["suggest"] and args.get("src"):
            item["suggest"]["src"] = args["src"]
            if Path(args["src"]).suffix.lower() in VIDEO_EXT and insert in ("visual", None):
                item["suggest"]["insert"] = "video"
            elif insert == "visual":
                item["suggest"]["insert"] = "image"
        flags = [f for f in flags if f]
        if flags:
            item["flag"] = "; ".join(flags)
        items.append(item)
    return {"script": str(script), "timing": timing, "items": items, "flags": sum(1 for x in items if x.get("flag"))}


def fmt_t(t):
    return "  --  " if t is None else f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser(description="Script directions -> work/directives.json")
    ap.add_argument("project")
    ap.add_argument("--script", help="script file (default: P/script.md or P/script.txt)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = C.Out(a.json)
    proj = C.need_project(a.project, [], a.json)
    script = Path(a.script).expanduser() if a.script else next((proj / n for n in SCRIPT_NAMES if (proj / n).exists()), None)
    if not script or not script.is_file():
        C.fail("No script found.", f"Save the script as {proj / 'script.md'} (directions in brackets), or pass --script FILE.", a.json)
    res = build(proj, script)
    C.write_json(proj / "work" / "directives.json", res)
    out.log(f"{script.name}: {len(res['items'])} directions, timing from {res['timing']}")
    for it in res["items"]:
        extra = ", ".join(f"{k} {v}" for k, v in it["args"].items() if k not in ("text", "fetch"))
        out.log(f"{it['n']:3}  {fmt_t(it['t0'])}-{fmt_t(it['t1'])}  {it['directive']:<10} {extra[:60]:<40} \"{it['line'][:60]}\"")
        if it.get("flag"):
            out.log(f"     FLAG ({it['raw'][:50]}): {it['flag']}")
    out.log(f"wrote {proj / 'work' / 'directives.json'} ({res['flags']} flagged)")
    out.result({"ok": True, "command": "script", **res})


if __name__ == "__main__":
    main()
