"""Timeline model for the split template: segments -> beats -> slices, word lookup, caption chunks.

All times are CUT time in seconds (30 fps). Nothing here touches HTML.
"""
import re

FPS = 30
EPS = 1e-4


def norm_word(t):
    return re.sub(r"[^\w'−-]+", "", t.lower().replace("’", "'")).strip("-")


def load_segments(edl, segs):
    """Merge segments.json (frames) with edl.json (mode/top, source of truth when present)."""
    by_id = {e["id"]: e for e in edl}
    out = []
    for s in segs:
        e = by_id.get(s["id"], {})
        out.append({
            "id": s["id"],
            "t0": s["frame"] / FPS,
            "t1": (s["frame"] + s["frames"]) / FPS,
            "mode": e.get("mode", s.get("mode", "split")),
            # edl.json is the source of truth: a segment present there without `top` has no insert
            "top": e.get("top") if e else s.get("top"),
            "src_in": s.get("src_in", s.get("in", 0.0)),
            "clip": s.get("clip", "c1"),
            "zoom": float(e.get("zoom", s.get("zoom", 1.0))),
            "line": e.get("line", s.get("line", "")),
        })
    return out


def normalize_items(top, hook=None):
    """top: None | "id" | {"insert","args"} | [..] -> list of {"insert","args"}."""
    if top is None or top == "same":
        return []
    if isinstance(top, str):
        top = [{"insert": top}]
    if isinstance(top, dict):
        top = [top]
    items = []
    for it in top:
        if isinstance(it, str):
            it = {"insert": it}
        it = dict(it)
        it.setdefault("args", {})
        if it.get("id") and not it.get("insert"):
            it["insert"] = it.pop("id")
        items.append(it)
    return items


class Words:
    def __init__(self, words):
        self.w = [{"text": x["text"], "start": float(x["start"]), "end": float(x["end"]), "n": norm_word(x["text"])}
                  for x in words]

    def find(self, spec, lo, hi=None):
        """spec 'word' or 'word:2' (2nd occurrence) -> start time of that word at/after lo (and < hi)."""
        m = re.match(r"^(.+?)(?::(\d+))?$", spec.strip())
        want, occ = norm_word(m.group(1)), int(m.group(2) or 1)
        for exact in (True, False):
            seen = 0
            for x in self.w:
                if x["start"] < lo - 0.06:
                    continue
                if hi is not None and x["start"] >= hi:
                    break
                if x["n"] == want or (not exact and x["n"].startswith(want)):
                    seen += 1
                    if seen == occ:
                        return x["start"]
        return None

    def find_end(self, spec, lo, hi=None):
        t = self.find(spec, lo, hi)
        if t is None:
            return None
        for x in self.w:
            if abs(x["start"] - t) < 1e-6:
                return x["end"]
        return t


def seg_at(segs, t):
    for s in segs:
        if s["t0"] - EPS <= t < s["t1"] - EPS:
            return s
    return segs[-1]


def resolve_beat_time(spec, segs, words):
    """project beat anchor -> cut time. Accepts at / at_src{seg,t} / at_word (+ optional seg)."""
    if "at" in spec:
        return float(spec["at"])
    if "at_src" in spec:
        a = spec["at_src"]
        s = next(x for x in segs if x["id"] == a["seg"])
        return min(max(s["t0"] + (float(a["t"]) - s["src_in"]), s["t0"]), s["t1"])
    if "at_word" in spec:
        s = next((x for x in segs if x["id"] == spec.get("seg")), None)
        lo, hi = (s["t0"], s["t1"]) if s else (0.0, None)
        t = words.find(spec["at_word"], lo, hi)
        if t is None:
            raise SystemExit(f"beat anchor word '{spec['at_word']}' not found")
        return max(t, lo)
    raise SystemExit(f"beat needs at / at_src / at_word: {spec}")


def build_beats(segs, project_beats, words, hook=None):
    beats = []
    for s in segs:
        if s["top"] == "same" and beats and beats[-1]["layout"] == s["mode"]:
            beats[-1]["t1"] = s["t1"]
            beats[-1]["segs"].append(s["id"])
            continue
        beats.append({"t0": s["t0"], "t1": s["t1"], "layout": s["mode"],
                      "items": normalize_items(s["top"], hook), "segs": [s["id"]], "origin": "edl"})
    for pb in project_beats or []:
        t0 = resolve_beat_time(pb, segs, words)
        s = seg_at(segs, t0)
        if "until" in pb:
            t1 = float(pb["until"])
        elif "until_word" in pb:
            t1 = words.find(pb["until_word"], t0 + 0.05) or s["t1"]
        elif "dur" in pb:
            t1 = t0 + float(pb["dur"])
        else:
            t1 = s["t1"]
        raw = pb.get("items")
        if raw is None and pb.get("insert"):
            raw = {"insert": pb["insert"], "args": pb.get("args", {})}
        nb = {"t0": t0, "t1": min(t1, s["t1"]), "layout": pb.get("layout", "split"),
              "items": normalize_items(raw, hook), "segs": [s["id"]], "origin": "project"}
        beats = _override(beats, nb)
    beats.sort(key=lambda b: b["t0"])
    for i, b in enumerate(beats):
        b["id"] = f"b{i}"
    return beats


def _override(beats, nb):
    out = []
    for b in beats:
        if b["t1"] <= nb["t0"] + EPS or b["t0"] >= nb["t1"] - EPS:
            out.append(b)
            continue
        if b["t0"] < nb["t0"] - EPS:
            out.append({**b, "t1": nb["t0"]})
        if b["t1"] > nb["t1"] + EPS:
            out.append({**b, "t0": nb["t1"], "anchor_t0": b.get("anchor_t0", b["t0"])})
    out.append(nb)
    return out


def build_slices(segs, beats):
    """Contiguous pieces with one segment and one beat: the unit for speaker placement and captions."""
    cuts = sorted({round(x, 4) for s in segs for x in (s["t0"], s["t1"])} |
                  {round(x, 4) for b in beats for x in (b["t0"], b["t1"])})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < EPS:
            continue
        mid = (a + b) / 2
        s = seg_at(segs, mid)
        bt = next((x for x in beats if x["t0"] <= mid < x["t1"]), None)
        out.append({"t0": a, "t1": b, "seg": s["id"], "layout": bt["layout"] if bt else s["mode"],
                    "beat": bt["id"] if bt else None})
    return out


END_P = re.compile(r"[.,?!;:]$")


def caption_chunks(words, slices, max_words=3, max_chars=26, gap=0.4, hold=0.25):
    """1-3 word chunks; never span a slice (cut/layout) boundary. Each chunk shows until the next starts."""
    bounds = [s["t0"] for s in slices]

    def slice_of(t):
        for s in slices:
            if s["t0"] - EPS <= t < s["t1"] - EPS:
                return s
        return slices[-1]

    chunks, cur = [], []
    for w in words.w:
        if cur:
            prev = cur[-1]
            same = slice_of(prev["start"]) is slice_of(w["start"])
            chars = sum(len(x["text"]) + 1 for x in cur) + len(w["text"])
            if (not same or len(cur) >= max_words or chars > max_chars or END_P.search(prev["text"])
                    or w["start"] - prev["end"] > gap):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    out = []
    for i, ch in enumerate(chunks):
        sl = slice_of(ch[0]["start"])
        t0 = max(ch[0]["start"], sl["t0"])
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else None
        end = ch[-1]["end"] + hold
        if nxt is not None and nxt - ch[-1]["end"] < gap:
            end = nxt
        t1 = min(end, sl["t1"])
        if t1 - t0 < 0.05:
            continue
        out.append({"text": " ".join(x["text"] for x in ch), "t0": t0, "t1": t1, "layout": sl["layout"],
                    "seg": sl["seg"]})
    return out
