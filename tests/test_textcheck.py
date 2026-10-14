"""textcheck.py unit tests (pure judging, no Chrome) + one optional browser run:
python -m unittest tests/test_textcheck.py (from the repo root)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import textcheck as T  # noqa: E402


def el(text="Hello world", **kw):
    base = {"id": "t1", "cls": "", "text": text, "cap": False, "lines": [[100, 100, 400, 150]], "nlines": 1,
            "words": len(text.split()), "last_len": len(text.split()[-1]), "last_line_words": 0, "ls": 0.0,
            "ws": "normal", "gaps": [0.25], "clip": None, "fs": 50}
    base.update(kw)
    return base


def samples(frames, els_fn):
    return [{"f": f, "els": els_fn(f)} for f in frames]


class Pure(unittest.TestCase):
    def test_clean_element_has_no_notes(self):
        self.assertEqual(T.element_notes(el()), [])

    def test_tracking_wordspacing_gap(self):
        kinds = [k for k, _, _ in T.element_notes(el(ls=-0.05, ws="-2px", gaps=[0.12, 0.3]))]
        self.assertEqual(sorted(kinds), ["gap", "tracking", "wordspacing"])
        self.assertEqual(T.element_notes(el(ls=-0.03)), [])          # exactly -0.03em is allowed
        self.assertEqual(T.element_notes(el(gaps=[0.18])), [])       # the threshold itself passes

    def test_wrap_only_for_headlines(self):
        two = {"nlines": 2, "lines": [[100, 100, 400, 150], [100, 160, 300, 210]]}
        self.assertIn("wrap", [k for k, _, _ in T.element_notes(el(**two))])
        self.assertNotIn("wrap", [k for k, _, _ in T.element_notes(el(cap=True, **two))])

    def test_orphan(self):
        kw = {"nlines": 2, "cap": True, "last_line_words": 1, "lines": [[100, 100, 400, 150], [100, 160, 200, 210]]}
        self.assertIn("orphan", [k for k, _, _ in T.element_notes(el("to max muscle protein synthesis", **kw))])
        self.assertNotIn("orphan", [k for k, _, _ in T.element_notes(el("max protein synthesis", **kw))])

    def test_overflow_and_clip(self):
        kinds = [k for k, _, _ in T.element_notes(el(lines=[[-10, 100, 300, 150]]))]
        self.assertEqual(kinds, ["overflow"])
        clipped = el(lines=[[100, 100, 400, 150]], clip=[90, 90, 300, 200, "panel"])
        self.assertEqual([k for k, _, _ in T.element_notes(clipped)], ["clip"])
        inside = el(lines=[[100, 100, 400, 150]], clip=[99, 99, 401, 151, "panel"])
        self.assertEqual(T.element_notes(inside), [])

    def test_overlap_threshold(self):
        self.assertAlmostEqual(T.overlap_frac([0, 0, 100, 100], [50, 0, 150, 100]), 0.5)
        self.assertEqual(T.overlap_frac([0, 0, 10, 10], [10, 0, 20, 10]), 0.0)
        a = el("A", id="a", lines=[[0, 0, 100, 100]])
        five = el("B", id="b", lines=[[95, 0, 195, 100]])            # 5% of the smaller box
        ten = el("B", id="b", lines=[[90, 0, 190, 100]])             # 10%
        self.assertEqual(T.overlap_notes([a, five]), [])
        self.assertEqual(T.overlap_notes([a, ten]), [("overlap", "a:A|b:B", "10%")])

    def test_doublecap(self):
        notes = T.sample_notes([el("one", id="c1", cap=True), el("two", id="c2", cap=True, lines=[[0, 500, 50, 550]])])
        self.assertIn(("doublecap", "one | two", "2 captions visible"), notes)

    def test_longest_run(self):
        self.assertEqual(T.longest_run([0, 3, 6, 12, 15, 18, 21], 3), (4, 12))
        self.assertEqual(T.longest_run([9], 3), (1, 9))

    def test_persistence_filter(self):
        transient = samples(range(0, 21, 3), lambda f: [el(gaps=[0.1])] if f < 12 else [el()])      # 4 samples
        self.assertEqual(T.judge(transient, 3, 8), {})
        lasting = samples(range(0, 30, 3), lambda f: [el(gaps=[0.1])])                             # 10 samples
        fails = T.judge(lasting, 3, 8)
        self.assertEqual(fails["gap"][0]["samples"], 10)
        self.assertEqual(fails["gap"][0]["first_frame"], 0)

    def test_hard_kinds_count_on_one_sample(self):
        one = samples([0, 3, 6], lambda f: [el(ls=-0.06)] if f == 3 else [el()])
        fails = T.judge(one, 3, 8)
        self.assertEqual(list(fails), ["tracking"])
        self.assertEqual(fails["tracking"][0]["first_frame"], 3)
        caps = samples([0, 3], lambda f: [el("x y", id="c1", cap=True), el("z w", id="c2", cap=True,
                                                                             lines=[[0, 500, 50, 550]])])
        self.assertIn("doublecap", T.judge(caps, 3, 8))

    def test_two_gaps_in_one_element_still_persist(self):
        """the original mjs reset the run when one element had two tight gaps in the same sample"""
        s = samples(range(0, 30, 3), lambda f: [el("What actually matters", gaps=[0.17, 0.17])])
        self.assertEqual(T.judge(s, 3, 8)["gap"][0]["samples"], 10)

    def test_describe(self):
        self.assertEqual(T.describe({}), "no text problems found")
        fails = {"gap": [{"what": "x:Hello world", "first_frame": 30, "samples": 9, "msg": "word gap 0.1em"}],
                 "overlap": [{"what": "a:A|b:B", "first_frame": 3, "samples": 9, "msg": "12%"}]}
        d = T.describe(fails)
        self.assertTrue(d.startswith("2 text problems: text overlaps other text at frame 3"))
        self.assertIn("cramped word gap at frame 30", d)


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_frame_count_precedence(self):
        self.assertIsNone(T.frame_count(self.tmp))
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "meta.json").write_text(json.dumps({"frames": 40}))
        self.assertEqual(T.frame_count(self.tmp), 40)
        (self.tmp / "segments.json").write_text(json.dumps([{"frames": 10}, {"frames": 20}]))
        self.assertEqual(T.frame_count(self.tmp), 30)
        (self.tmp / "layout_boxes.json").write_text(json.dumps({"frames": 99}))
        self.assertEqual(T.frame_count(self.tmp), 99)
        self.assertEqual(T.frame_count(self.tmp, 12), 12)

    def test_instrument_and_canvas(self):
        src = '<html><head><title>x</title></head><body><div id="root" data-width="720" data-height="1280"></div></body></html>'
        page = T.instrument(src, self.tmp, [0, 3])
        self.assertIn('<head><base href="file://', page)
        self.assertLess(page.index("<script>"), page.index("</body>"))
        self.assertIn("var FRAMES = [0, 3]", page)
        self.assertEqual(T.canvas_size(src), (720, 1280))
        self.assertEqual(T.canvas_size("<body></body>", [500, 0]), T.DEFAULT_CANVAS)
        self.assertEqual(T.canvas_size("<body></body>", [500, 900]), (500, 900))

    def test_check_skips_without_index(self):
        r = T.check(self.tmp)
        self.assertTrue(r["pass"])
        self.assertTrue(r["skipped"])
        self.assertEqual(r["name"], "text_collision")
        self.assertFalse((self.tmp / "qa").exists())


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#000} #root{position:relative;width:1080px;height:1920px}
.t{position:absolute;font:700 80px/1 sans-serif;color:#fff;white-space:nowrap}
</style></head><body><div id="root" data-width="1080" data-height="1920">
<div id="a" class="t" style="left:100px;top:400px">OVERLAP ONE</div>
<div id="b" class="t" style="left:140px;top:420px">OVERLAP TWO</div>
<div id="c" class="t" style="left:100px;top:1200px">Clean line</div>
</div><script>window.__timelines = window.__timelines || {}; window.__timelines.main = {seek: function () {}};</script>
</body></html>"""


@unittest.skipUnless(T.find_chrome(), "no Chrome found")
class Browser(unittest.TestCase):
    def test_synthetic_overlap_page(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "index.html").write_text(PAGE, encoding="utf-8")
            rep = T.run(tmp, frames=12, step=1, persist=8)
            self.assertFalse(rep["pass"])
            self.assertEqual(rep["samples"], 12)
            self.assertEqual(list(rep["fails"]), ["overlap"])
            self.assertEqual(rep["fails"]["overlap"][0]["what"], "a:OVERLAP ONE|b:OVERLAP TWO")
            self.assertTrue((tmp / "qa" / "textcheck.json").is_file())
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["index.html", "qa"])   # nothing else written
            r = T.check(tmp, frames=12, step=1)
            self.assertFalse(r["pass"])
            self.assertIn("text overlaps other text at frame 0", r["detail"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
