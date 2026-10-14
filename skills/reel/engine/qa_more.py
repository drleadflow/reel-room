"""qa_more.py: three gates ported from the showcase showcase work, run by qa.py (names in qa.CHECKS).

  text_collision    textcheck.py: headless Chrome seeks the composition and measures every text line (overlaps,
                    overflow, wraps, orphans, tight word gaps, tracking, two captions at once). Skipped without
                    index.html or Chrome.
  caption_phrasing  capcheck.py: a caption never ends on a binding word or splits a number from its unit while the
                    next one follows within 0.4 s; captions never overlap in time.
  aroll_repeats     aroll_fix.py: no repeated frames that the cut added (compared with the source, so source stills
                    are fine). assemble.py already fixes these itself unless project.json "aroll_fix" is "off".
  numbers_verified  numgate.py: every number on screen (captions, set headlines, cards, heroes, inserts) is in the
                    numcheck.py ledger as verified or confirmed by hand (evidence data: from work/sources.txt).
Each check returns {name, pass, detail, label[, skipped]} and never raises.
"""
from __future__ import annotations

NAMES = ("text_collision", "caption_phrasing", "aroll_repeats", "numbers_verified")


def _safe(name, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001  a broken gate must not crash the whole QA run
        return {"name": name, "pass": False, "detail": f"could not run this check: {e}", "label": name}


def run(project, only) -> list:
    out = []
    if "text_collision" in only:
        import textcheck
        out.append(_safe("text_collision", textcheck.check, project))
    if "caption_phrasing" in only:
        import capcheck
        out.append(_safe("caption_phrasing", capcheck.check, project))
    if "aroll_repeats" in only:
        import aroll_fix
        out.append(_safe("aroll_repeats", aroll_fix.check, project))
    if "numbers_verified" in only:      # numgate.py: every on-screen number verified against the audio (numcheck.py)
        import numgate
        out.append(_safe("numbers_verified", numgate.check, project))
    return out
