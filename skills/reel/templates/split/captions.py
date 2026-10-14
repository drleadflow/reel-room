"""Caption chunking and caption modes.

Modes (project.json "captions": {"mode": ...}):
  pill  1-3 words in a dark pill (split: on the seam; full: at chest, below the chin). Default.
  word  ONE word at a time, swapping between a bold sans and an italic serif accent (motion-editorial).
        Accent words: captions.accent (list of words), else auto (numbers, words of 7+ letters, names).

Chunking never spans a cut/layout slice, never leaves an orphan (a lone weak word such as "a", "the", "to", or a
chunk that ends on a weak word when the next chunk follows straight on), and keeps the text exactly as words.json.
"""
import re

from timeline import EPS

WEAK = {"a", "an", "the", "to", "of", "i", "i'm", "my", "your", "and", "with", "about", "on", "in", "is", "that",
        "for", "it", "as", "at", "or", "but", "if", "so", "be", "you", "was", "are", "would", "will", "we", "me"}
END_P = re.compile(r"[.,?!;:]$")


def _bare(t):
    return re.sub(r"[^\w']+", "", t.lower().replace("’", "'"))


def _slice_of(slices, t):
    for s in slices:
        if s["t0"] - EPS <= t < s["t1"] - EPS:
            return s
    return slices[-1]


def phrases(words, slices, gap=0.4):
    """Split the word list at punctuation, pauses and slice boundaries."""
    out, cur = [], []
    for w in words.w:
        if cur:
            prev = cur[-1]
            if (_slice_of(slices, prev["start"]) is not _slice_of(slices, w["start"]) or END_P.search(prev["text"])
                    or w["start"] - prev["end"] > gap):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


# a chunk never ends on one of these while the phrase goes on (QA caption_phrasing / engine/capcheck.py BIND + a few
# intensifiers); a cut may still force the break, phrases() never joins across a cut
BIND = {"a", "an", "the", "to", "of", "per", "and", "or", "for", "at", "your", "my", "in", "on", "with", "that", "about",
        "if", "can", "only", "is", "than", "versus", "how", "many", "you", "you're", "i'll", "from", "this", "so", "but",
        "be", "should", "max", "found", "very", "really", "completely"}
STRETCH_WORDS, STRETCH_CHARS = 1, 8   # one extra word / a few chars when that is the only way to avoid a bad break


def _cost(chunk, max_words, max_chars):
    chars = sum(len(x["text"]) + 1 for x in chunk) - 1
    c = 0.0
    if len(chunk) > max_words or chars > max_chars:
        if len(chunk) > max_words + STRETCH_WORDS or chars > max_chars + STRETCH_CHARS:
            return 1e6
        c += 12
    if len(chunk) == 1 and _bare(chunk[0]["text"]) in WEAK:
        c += 30
    if len(chunk) == 1:
        c += 15
    return c


NUMBER = re.compile(r"^[$£€]?\d[\d.,]*(%|[kKmMbBxX])?$")


def _is_number(text) -> bool:
    """'5', '$60', '0.24', '30%': a caption chunk never ends on one while the phrase goes on."""
    return bool(NUMBER.match(str(text).strip("\"'()")))


def split_phrase(ph, max_words, max_chars):
    """Best split of one phrase into chunks of <= max_words (DP on a small cost). A chunk that ends on a binding word
    while the phrase continues costs more than a one-word chunk or a slightly long one."""
    n = len(ph)
    best = [(0.0, [])] + [(1e9, None)] * n
    for i in range(1, n + 1):
        for k in range(1, max_words + STRETCH_WORDS + 1):
            j = i - k
            if j < 0:
                break
            chunk = ph[j:i]
            c = best[j][0] + _cost(chunk, max_words, max_chars)
            if i < n and (_bare(chunk[-1]["text"]) in BIND or _is_number(chunk[-1]["text"])):
                c += 40           # dangling binding word, or a number split from its noun / unit ('the 5 | things')
            elif i < n and _bare(chunk[-1]["text"]) in WEAK:
                c += 5
            c += 1  # prefer fewer chunks
            if c < best[i][0]:
                best[i] = (c, best[j][1] + [chunk])
    return best[n][1]


def chunks(words, slices, max_words=3, max_chars=26, gap=0.4, hold=0.25, mode="pill"):
    if mode == "word":
        groups = [[w] for w in words.w]
    else:
        groups = []
        for ph in phrases(words, slices, gap):
            groups.extend(split_phrase(ph, max_words, max_chars))
    out = []
    for i, ch in enumerate(groups):
        sl = _slice_of(slices, ch[0]["start"])
        mid = (ch[0]["start"] + ch[0]["end"]) / 2
        if mid >= sl["t1"] - EPS:   # starts a frame or two before a cut but is mostly heard after it: it belongs to that shot
            sl = _slice_of(slices, mid)
        t0 = max(ch[0]["start"], sl["t0"])
        nxt = groups[i + 1][0]["start"] if i + 1 < len(groups) else None
        end = ch[-1]["end"] + hold
        if nxt is not None and nxt - ch[-1]["end"] < gap:
            end = nxt
        if nxt is not None:
            end = min(end, nxt)
        t1 = min(end, sl["t1"])
        if t1 - t0 < 0.05:
            # too short to read on its own (a word right before a cut): show it from a frame earlier if possible
            t0 = max(sl["t0"], t1 - 0.1)
            if t1 - t0 < 0.03:
                continue
        if out and out[-1]["t1"] > t0:   # never two captions on screen at once
            out[-1]["t1"] = t0
        out.append({"text": " ".join(x["text"] for x in ch), "t0": t0, "t1": t1, "layout": sl["layout"],
                    "seg": sl["seg"], "n": len(ch)})
    return [c for c in out if c["t1"] - c["t0"] >= 0.03]


def orphans(chs):
    """QA helper: chunks that are orphans = a lone word cut off from its own phrase (it follows or precedes a chunk of
    the same sentence without a pause), or a lone weak word anywhere. Word mode is exempt (one word is the style)."""
    bad = []
    for i, c in enumerate(chs):
        ws = c["text"].split()
        if len(ws) != 1:
            continue
        prev_tied = i > 0 and chs[i - 1]["seg"] == c["seg"] and abs(chs[i - 1]["t1"] - c["t0"]) < 0.05 \
            and not END_P.search(chs[i - 1]["text"])
        next_tied = i + 1 < len(chs) and chs[i + 1]["seg"] == c["seg"] and abs(chs[i + 1]["t0"] - c["t1"]) < 0.05 \
            and not END_P.search(ws[0])
        if _bare(ws[0]) in WEAK or prev_tied or next_tied:
            bad.append(c["text"])
    return bad


def word_text(t, strip=True):
    """Display text of one word in word mode: trailing commas/periods dropped (the look), the word itself unchanged."""
    return re.sub(r"[.,;:]+$", "", t) if strip else t


def is_accent(text, accent_list, i):
    b = _bare(text)
    if accent_list is not None:
        return b in {_bare(a) for a in accent_list}
    return bool(re.match(r"^\d", b)) or len(b) >= 7


# ----------------------------------------------------------------------------- no repeats
from html.parser import HTMLParser  # noqa: E402


class _TextBoxes(HTMLParser):
    """Collect (t0, t1, text) of every on-screen text element (data-box text/glyph) in a composition fragment."""
    VOID = {"br", "img", "input", "meta", "link", "hr", "source", "path", "circle", "line", "rect"}

    def __init__(self):
        super().__init__()
        self.stack, self.out = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        a = dict(attrs)
        rec = None
        if a.get("data-box") in ("text", "glyph") and a.get("data-t0") is not None:
            rec = [float(a["data-t0"]), float(a["data-t1"]), []]
        self.stack.append((tag, rec))

    def handle_endtag(self, tag):
        while self.stack:
            t, rec = self.stack.pop()
            if rec is not None:
                self.out.append((rec[0], rec[1], " ".join(rec[2])))
            if t == tag:
                break

    def handle_data(self, data):
        for _t, rec in self.stack:
            if rec is not None:
                rec[2].append(data)


def shown_text(html_fragment):
    p = _TextBoxes()
    p.feed(html_fragment)
    return [(t0, t1, {_bare(w) for w in re.split(r"[\s/·=+]+", txt) if _bare(w)}) for t0, t1, txt in p.out]


def hide_repeats(chs, shown, mode, fresh=2.0):
    """Mark captions whose words are already on screen as typography at that moment (never repeat on-screen text).
    Only FRESH type counts (landed within `fresh` s before the caption): a title that has been up for a while is
    scenery, not a typography moment. word mode: the word itself is on screen; pill mode: every word of the chunk is."""
    cand = []
    for c in chs:
        a, z = c["t0"], c["t1"]
        vis = set()
        for t0, t1, ws in shown:  # type that is up (or lands) while the caption is up, and landed recently
            if t0 - 0.02 < z and t1 > a + 0.03 and a - t0 <= fresh:
                vis |= ws
        words = [_bare(w) for w in c["text"].split() if _bare(w)]
        cand.append(bool(words) and all(w in vis for w in words))
    n, i = 0, 0
    while i < len(chs):   # an echo is a run of consecutive captions on screen as type, with at least one strong word:
        if not cand[i]:    # "crash out" under a CRASH OUT title is hidden, a lone "you" under WHY YOU is not
            i += 1
            continue
        j = i
        while j + 1 < len(chs) and cand[j + 1] and chs[j + 1]["t0"] - chs[j]["t1"] < 0.3:
            j += 1
        run = [w for c in chs[i:j + 1] for w in (_bare(x) for x in c["text"].split()) if w]
        if any(w not in WEAK for w in run):
            for c in chs[i:j + 1]:
                c["hidden"] = True
                n += 1
        i = j + 1
    return n


def pill_html(text, cfg):
    """Caption pill inner html. Calm captions (cfg "calm", the kallaway preset) colour at most `accent_max` accent
    words (cfg "accent") per chunk; otherwise the escaped text exactly as before."""
    import html as _h
    if not cfg.get("calm") or not cfg.get("accent"):
        return _h.escape(str(text), quote=True)
    acc = {re.sub(r"[^\w']+", "", a.lower()) for a in cfg["accent"]}
    left, out = int(cfg.get("accent_max", 1)), []
    for w in str(text).split(" "):
        if left > 0 and re.sub(r"[^\w']+", "", w.lower()) in acc:
            out.append(f'<span class="cap-acc">{_h.escape(w, quote=True)}</span>')
            left -= 1
        else:
            out.append(_h.escape(w, quote=True))
    return " ".join(out)
