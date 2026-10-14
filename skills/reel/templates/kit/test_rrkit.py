"""Kit smoke tests: word anchors (ordered search, ^ end, :n, offsets, fallback), both engine adapters, registry.
Run: python3 test_rrkit.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rrkit  # noqa: E402

W = [{"text": "I", "start": 0.2, "end": 0.3}, {"text": "typed", "start": 0.35, "end": 0.7},
     {"text": "the", "start": 0.8, "end": 0.9}, {"text": "prompt,", "start": 1.0, "end": 1.4},
     {"text": "then", "start": 1.6, "end": 1.8}, {"text": "the", "start": 2.0, "end": 2.1},
     {"text": "result", "start": 2.2, "end": 2.6}]


def close(a, b):
    return abs(a - b) < 1e-6


def test_anchors():
    k = rrkit.Kit(None, W)
    cur = k.cursor()
    assert close(cur("@typed"), 0.31)                 # visual lead 0.04
    assert close(cur("@the"), 0.76)
    assert close(cur("@the"), 1.96)                   # ordered: the second 'the'
    assert close(k.cursor()("@prompt^"), 1.4)         # word end, no lead
    assert close(k.cursor()("@the:2+0.1"), 2.06)
    assert close(k.cursor()("@missing", 0.5), 0.5)    # fallback
    assert close(rrkit.Kit(None, W, base=1.0).cursor()(0.5), 1.5)   # numbers are relative to base


class Ctx:
    def __init__(self):
        self.tw, self.events, self.n, self.brand = [], [], 0, rrkit.DEFAULT_BRAND

        class Words:
            w = W
        self.words = Words()

    def event(self, t, kind, what=""):
        self.events.append((t, kind, what))

    def uid(self, p):
        self.n += 1
        return f"{p}{self.n}"


class TL:
    def __init__(self):
        self.js, self.cues = [], []

    def cue(self, t, name, gain_db=0.0):
        self.cues.append((t, name))


def test_adapters():
    cx = Ctx()
    k = rrkit.Kit.for_split(cx, {"t0": 0.0, "t1": 3.0})
    p = k.typer("make captions", at=0.1, type_at="@typed", type_until="@prompt^", send="@then", done="done",
                done_at="@result")
    h1, h2 = rrkit.mount(cx, p), rrkit.mount(cx, k.pill("NEW", at=0.5))
    assert "data-rrk" in h1 and "data-rrk" not in h2 and len(cx.tw) == 2 and cx.events
    assert p.t1 >= 3.0 and all(e[1] in rrkit.SOUND_OF for e in cx.events)
    tl = TL()
    rrkit.mount(tl, rrkit.Kit(None, W).odometer(42, at=0.2, land="@prompt"))
    assert tl.cues and tl.js
    assert "—" not in h1 and "–" not in h1          # no em/en dashes on screen


def test_registry():
    k = rrkit.Kit(None, W)
    for cid, info in rrkit.COMPONENTS.items():
        assert hasattr(rrkit.Kit, info["method"]), cid
        assert info["say"], cid
    p = rrkit.build(k, "checklist-tick", items=["a", "b"], ticks=["@typed", "@prompt"])
    assert p.comp == "checklist-tick" and p.events("light") and len(p.events("full")) >= len(p.events("light"))
    assert p.events("off") == []


def test_head_bubble():
    k = rrkit.Kit(None, W)
    face = [(0.0, 540, 1310, 190), (3.0, 560, 1300, 190)]
    p = k.head_bubble(at=0.2, back="@result", corner="tl", size=300, face=face, clip=(0, 960, 1080, 1920),
                      plate={"x": 0, "y": 312, "scale": 1, "ox": 540, "oy": 0}, behind="<div class='dg'></div>",
                      label="me", vignette=0.16)
    rows = p.js[0].split('"rows":')[1]
    assert p.comp == "head-bubble" and "RRK.bubble(" in p.js[0] and "hb-cam" in p.meta["cam_sel"]
    import json as _j
    cfg = _j.loads(p.js[0][p.js[0].index(",{") + 1:-2])
    first, last = cfg["rows"][0], cfg["rows"][-1]
    # hand-off: the first and last frames are the plate exactly (identity move, mask covers the clip region)
    assert first[1:4] == [1.0, 0.0, 0.0] and last[1:4] == [1.0, 0.0, 0.0] and first[6] > 600 and last[6] > 600
    assert close(p.t0, 0.2) and close(cfg["back"], 2.18) and close(p.t1, cfg["back"] + 0.56)
    hold = [r for r in cfg["rows"] if 0.9 < r[0] / 30 < 2.0]
    for r in hold:   # landed: the face point maps to the corner centre, the circle is size/2 on screen
        s, tx, ty, mx, my, R = r[1], r[2], r[3], r[4], r[5], r[6]
        assert abs(s * mx + tx - 210) < 1.5 and abs(s * my + ty - 400) < 1.5 and abs(s * R - 150) < 4
    assert 'clip-path:inset(960px 0px 0px 0px)' in p.html and "translate(0px,312px)" in p.html
    assert 'data-box="text"' in p.html and rows.startswith("[[")
    try:
        k.head_bubble(at=0.2, corner="bl")
        assert False, "bad corner must raise"
    except ValueError:
        pass
    assert "head-bubble" in rrkit.COMPONENTS and "kit_pip.js" in rrkit.JS_FILES


if __name__ == "__main__":
    test_anchors()
    test_adapters()
    test_registry()
    test_head_bubble()
    print("rrkit tests: ok")
