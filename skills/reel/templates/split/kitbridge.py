"""kitbridge.py: the component kit (templates/kit/rrkit.py) inside the split engine: one import path, one Kit per beat."""
import os
import sys

KIT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kit")
if KIT_DIR not in sys.path:
    sys.path.insert(0, KIT_DIR)
import rrkit  # noqa: E402


def kit(cx, beat):
    """A Kit whose plain numbers are seconds after the beat start and whose anchors search inside the beat."""
    return rrkit.Kit.for_split(cx, beat)


def mount(cx, piece, sfx_level="light"):
    """The piece's html (the kit runtime is inlined once per page); tweens go to cx.tw, sounds to cx.event. The piece's
    smaller moments (rows, ticks, a message landing) that make no sound at this level are still visual events: they
    are logged silent (kind "cut"), so QA's event density sees what is on screen."""
    html = rrkit.mount(cx, piece, sfx_level=sfx_level)
    heard = {(e["t"], e["what"]) for e in piece.events(sfx_level)}
    for e in piece.events("full"):
        if (e["t"], e["what"]) not in heard and e["kind"] not in ("type", "tick"):
            cx.event(e["t"], "cut", f"{piece.comp}: {e['what']} (visual)")
    return html
