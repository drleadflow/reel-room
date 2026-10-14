"""Shared helpers for the plan compiler: inputs, word windows, anchors, verbatim text helpers, safe writes."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

FPS = 30
EM_DASH = "—"
ARROWS = ("→", "->", "=>", " / ", " vs ")
OWNED_PROJECT_KEYS = ("style", "template", "style_cfg", "motion", "hook", "beats", "overlays", "captions", "card",
                      "stage", "split", "deck", "compiled")
OWNED_EDL_KEYS = ("mode", "top", "punch", "punch_at", "motion")


class CompileError(ValueError):
    """A plan or project problem the user has to fix. The message names the beat."""


def jload(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is None:
            raise CompileError(f"missing {p}")
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise CompileError(f"{p} is not valid JSON: {exc}") from exc


def jwrite(path, data) -> None:
    """Write JSON atomically (tmp file + rename), so a failed compile never leaves half a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, p)


def backup_once(src, dest) -> None:
    """Keep the pre-compile copy of a file the compiler rewrites (first compile only)."""
    if Path(src).exists() and not Path(dest).exists():
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def edl_list(edl) -> list:
    return edl if isinstance(edl, list) else list(edl.get("segments", []))


def windows(segments: list) -> dict:
    """segments.json -> {seg id: (t0, t1)} in cut seconds (frame exact)."""
    out = {}
    for s in segments:
        if "frame" not in s or "frames" not in s:
            raise CompileError(f"segments.json entry {s.get('id')!r} has no frame/frames: run assemble.py first")
        out[s["id"]] = (s["frame"] / FPS, (s["frame"] + s["frames"]) / FPS)
    return out


def load_inputs(proj: Path, plan_rel: str) -> dict:
    """Everything the compiler reads. Fails with a plain message when a file is missing."""
    plan_path = proj / plan_rel
    edl = edl_list(jload(proj / "edl.json"))
    return {"proj": proj, "plan_path": plan_path, "plan": jload(plan_path), "pj": jload(proj / "project.json", {}),
            "edl": edl, "win": windows(jload(proj / "segments.json")), "words": jload(proj / "words.json"),
            "facepos": jload(proj / "work" / "facepos.json", {})}


def norm(word: str) -> str:
    """Same normalisation as the split engine's word finder (timeline.norm_word)."""
    return re.sub(r"[^\w'−-]+", "", str(word).lower().replace("’", "'")).strip("-")


def seg_words(words: list, win: tuple) -> list:
    t0, t1 = win
    return [w for w in words if t0 - 0.06 <= float(w["start"]) < t1]


def anchor_for(word: str, in_seg: list) -> str | None:
    """'@token' for a plan anchor word when it is spoken inside the segment (exact, then prefix, like the engine).
    Tokens are made safe for both anchor parsers (no '+', ':', '^', no '-<digit>')."""
    want = norm(word)
    if re.search(r"-\d", want):
        want = want.split("-")[0]
    if not want:
        return None
    toks = [norm(w["text"]) for w in in_seg]
    if want in toks or any(t.startswith(want) for t in toks):
        return "@" + want
    return None


def first_anchor(in_seg: list) -> str | None:
    """The first content word of a segment as an anchor (fallback when the plan's word is not in the words)."""
    for w in in_seg:
        tok = norm(w["text"])
        if len(tok) > 2:
            return anchor_for(tok, in_seg)
    return None


def split_items(text: str) -> list:
    """List items from on-screen text, verbatim: one per line, else comma separated."""
    parts = [p.strip() for p in str(text).split("\n") if p.strip()]
    for sep in (",", " / ", ";"):
        if len(parts) == 1:
            parts = [p.strip() for p in parts[0].split(sep) if p.strip()]
    return parts


def number_in(text: str):
    """(value, rest) when the text leads with or holds one number ('100%', '7 days'), else (None, text)."""
    m = re.search(r"[$£€]?\d+(?:[.,]\d+)?\s?[%xX+]?", str(text))
    if not m:
        return None, text
    rest = (text[:m.start()] + text[m.end():]).strip(" :-")
    return m.group(0).strip(), rest


def arrow_split(text: str):
    """('left', 'arrow', 'right') when the text is 'A -> B', else None."""
    for arrow in ARROWS:
        if arrow in str(text):
            left, right = (x.strip() for x in str(text).split(arrow, 1))
            if left and right:
                return left, arrow, right
    return None


def title_lines(title: str) -> tuple:
    """A title split into 2 balanced lines on a word boundary (verbatim words)."""
    words = str(title).split()
    if len(words) < 2:
        return title, ""
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]), " ".join(words[best:])


def no_dash(where: str, text: str) -> str:
    if EM_DASH in str(text):
        raise CompileError(f"{where}: on-screen text {text!r} has an em dash; rewrite it without one")
    return text
