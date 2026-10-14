"""Split-engine presets: kallaway feed timing, explicit settings win, face mask for head bubbles, calm captions.
python -m unittest tests/test_presets.py (from the repo root)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SPLIT = Path(__file__).resolve().parent.parent / "skills" / "reel" / "templates" / "split"
sys.path.insert(0, str(SPLIT))
import captions  # noqa: E402
import feed  # noqa: E402
import presets  # noqa: E402
import report  # noqa: E402


def words(n=60, step=0.33):
    return [{"text": f"word{i}", "start": round(0.1 + i * step, 3), "end": round(0.1 + i * step + 0.25, 3)} for i in range(n)]


class Feed(unittest.TestCase):
    def test_chop_cadence(self):
        for span in (2.0, 4.6, 5.4, 7.3, 11.0):
            cuts = feed.chop(0.0, span, words(), 1.0, 0.8, 1.4)
            lens = [b - a for a, b in cuts]
            self.assertAlmostEqual(sum(lens), span, places=3)
            self.assertTrue(all(0.8 - 1e-6 <= x <= 1.4 + 1e-6 for x in lens), (span, lens))

    def test_plan_pins_then_cards(self):
        w = words()
        srcs = [{"src": "a.mp4"}, {"src": "b.png", "word": "word12"}]
        beats, rep = feed.plan([(0.0, 6.0)], w, srcs, {}, {"every": 1.0})
        self.assertEqual(rep["pictures"], len(beats))
        pinned = next(b for b in beats if b["args"].get("src") == "b.png")
        self.assertTrue(pinned["at"] <= w[12]["start"] < pinned["until"])
        self.assertEqual(rep["cards"], rep["pictures"] - 2)
        self.assertTrue(all(b["insert"] in feed.FEED_INSERTS for b in beats))


class Preset(unittest.TestCase):
    def project(self):
        d = tempfile.mkdtemp()
        segs = [{"id": "a", "frame": 0, "frames": 90}, {"id": "b", "frame": 90, "frames": 150},
                {"id": "c", "frame": 240, "frames": 90}]
        Path(d, "segments.json").write_text(json.dumps(segs))
        edl = [{"id": "a", "mode": "split", "line": "One two."}, {"id": "b", "mode": "split", "purpose": "analogy", "line": "x"},
               {"id": "c", "mode": "full", "line": "y", "motion": {"camera": "punch"}}]
        return d, edl

    def test_no_preset_is_untouched(self):
        d, edl = self.project()
        pj = {"style": "split-deck"}
        self.assertIs(presets.apply(d, pj, edl, words())[0], pj)

    def test_explicit_wins(self):
        d, edl = self.project()
        pj, e2 = presets.apply(d, {"preset": "kallaway", "motion": {"sfx": "off"}}, edl, words())
        self.assertEqual(pj["motion"]["sfx"], "off")
        self.assertEqual(pj["motion"]["transitions"], "off")
        self.assertTrue(pj["captions"]["calm"])
        modes = {e["id"]: e["mode"] for e in e2}
        self.assertEqual(modes, {"a": "split", "b": "full", "c": "split"})
        cams = {e["id"]: e["motion"].get("camera") for e in e2}
        self.assertEqual(cams, {"a": "still", "b": "still", "c": "punch"})   # c's own camera wins
        self.assertEqual(e2[1]["motion"]["level"], "simple")
        self.assertTrue(pj["beats"] and pj["_preset"]["feed"]["pictures"] == len(pj["beats"]))
        self.assertEqual(edl[2]["mode"], "full")                              # input not mutated

    def test_pip_mask(self):
        pl = [{"t0": 0.0, "t1": 4.0, "visible": True, "face": {"cx": 1}}, {"t0": 4.0, "t1": 8.0, "visible": True, "face": {}}]
        out = report.pip_mask(pl, [(2.0, 5.0)])
        inside = [p for p in out if p.get("pip")]
        self.assertEqual([(p["t0"], p["t1"]) for p in inside], [(2.0, 4.0), (4.0, 5.0)])
        self.assertTrue(all(not p["visible"] for p in inside))
        self.assertEqual(sum(p["t1"] - p["t0"] for p in out), 8.0)
        self.assertTrue(pl[0]["visible"])

    def test_overlays_and_free(self):
        d, edl = self.project()
        edl[0]["bubble"] = {"at": 0.0}
        pj, e2 = presets.apply(d, {"preset": "kallaway", "banner": "ONE TWO THREE", "cta": {"keyword": "GO", "from": 6.0}},
                               edl, words())
        names = [o["insert"] for o in pj["overlays"]]
        self.assertEqual(names, ["topic_banner", "head_bubble", "comment_cta"])
        self.assertEqual(pj["_preset"]["covered"], [[0.0, 3.0], [6.0, 11.0]])
        for b in pj["beats"]:      # no feed picture inside a covered window
            self.assertTrue(b["until"] <= 6.0 + 1e-6 and b["at"] >= 3.0 - 1e-6, b)

    def test_preset_inserts_never_shadow_stock(self):
        import importlib.util
        import kallaway
        # load the SPLIT template's compose.py by path: another test may already have put the editorial-ui
        # compose.py (no LIB) in sys.modules under the same name, which made this test fail only in a full run
        spec = importlib.util.spec_from_file_location("split_compose_for_test", SPLIT / "compose.py")
        compose = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compose)
        stock = set(compose.LIB) | set(compose.ALIASES)
        self.assertEqual(stock & (set(kallaway.INSERTS) | set(feed.INSERTS)), set())

    def test_calm_caption_accent(self):
        cfg = {"calm": True, "accent": ["7", "5"], "accent_max": 1}
        self.assertEqual(captions.pill_html("over 7, 5", cfg), 'over <span class="cap-acc">7,</span> 5')
        self.assertEqual(captions.pill_html("a <b>", {}), "a &lt;b&gt;")


if __name__ == "__main__":
    unittest.main()
