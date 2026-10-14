"""capcheck.py unit tests (pure rules + layout_boxes.json shapes): python -m unittest tests/test_capcheck.py
(from the repo root)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import capcheck as CC  # noqa: E402


def caps(*spec):
    """caps(("text", t0, t1), ...)"""
    return [{"text": t, "t0": a, "t1": b} for t, a, b in spec]


class Rules(unittest.TestCase):
    def test_binding_word_break_without_pause(self):
        bad = CC.phrasing_findings(caps(("the ideal amount of", 0.0, 1.0), ("protein every day", 1.1, 2.0)))
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("mid-phrase break at 1.00"))

    def test_break_forced_by_a_cut_is_allowed(self):
        c = caps(("the ideal amount of", 0.0, 1.0), ("protein every day", 1.1, 2.0))
        self.assertEqual(CC.phrasing_findings(c, cuts=[1.05]), [])
        self.assertEqual(len(CC.phrasing_findings(c, cuts=[1.6])), 1)      # a cut elsewhere does not excuse it

    def test_lone_word_left_by_a_cut_is_allowed(self):
        c = caps(("we start with", 0.0, 1.0), ("blood", 1.05, 1.3), ("work and labs", 1.35, 2.0))
        self.assertTrue(any("orphan" in x for x in CC.phrasing_findings(c)))
        self.assertFalse(any("orphan" in x for x in CC.phrasing_findings(c, cuts=[1.32])))

    def test_seg_change_forces_the_break(self):
        c = [{"text": "the ideal amount of", "t0": 0.0, "t1": 1.0, "seg": "a"},
             {"text": "protein every day", "t0": 1.05, "t1": 2.0, "seg": "b"}]
        self.assertEqual(CC.phrasing_findings(c), [])
        c[1]["seg"] = "a"
        self.assertEqual(len(CC.phrasing_findings(c)), 1)

    def test_one_word_segment_is_not_an_orphan(self):
        c = [{"text": "and then it", "t0": 0.0, "t1": 1.0, "seg": "a"}, {"text": "plummeted.", "t0": 1.05, "t1": 1.5, "seg": "b"},
             {"text": "nobody saw it coming", "t0": 1.55, "t1": 2.5, "seg": "c"}]
        self.assertEqual(CC.phrasing_findings(c), [])

    def test_break_ok_with_pause_or_punctuation(self):
        self.assertEqual(CC.phrasing_findings(caps(("the ideal amount of", 0.0, 1.0), ("protein now", 1.5, 2.0))), [])
        self.assertEqual(CC.phrasing_findings(caps(("so much to", 0.0, 1.0), ("do today", 1.5, 2.0))), [])
        self.assertEqual(CC.phrasing_findings(caps(("eat the protein,", 0.0, 1.0), ("then rest", 1.0, 2.0))), [])

    def test_number_split_from_unit(self):
        bad = CC.phrasing_findings(caps(("aim for 1.6", 0.0, 1.0), ("grams per kilo", 1.05, 2.0)))
        self.assertEqual(len(bad), 1)
        self.assertIn("'aim for 1.6'", bad[0])

    def test_time_overlap(self):
        bad = CC.phrasing_findings(caps(("first line here", 0.0, 1.2), ("second line here", 1.0, 2.0)))
        self.assertEqual(bad, ["overlap 'first line here' / 'second line here' at 1.00"])

    def test_orphan_in_phrase_mode(self):
        c = caps(("protein matters most", 0.0, 1.0), ("really", 1.05, 1.3), ("for muscle growth", 1.35, 2.0))
        self.assertEqual(CC.phrasing_findings(c), ["orphan word 'really' at 1.05"])
        also = caps(("protein matters most", 0.0, 1.0), ("also", 1.05, 1.3), ("for muscle growth", 1.35, 2.0))
        self.assertEqual(CC.phrasing_findings(also), [])
        lone = caps(("protein matters most", 0.0, 1.0), ("really", 1.5, 1.8), ("for muscle growth", 2.3, 3.0))
        self.assertEqual(CC.phrasing_findings(lone), [])

    def test_word_mode_skips_orphans(self):
        words = caps(("What's", 0.0, 0.3), ("the", 0.3, 0.4), ("ideal", 0.4, 0.7), ("amount", 0.7, 1.0))
        self.assertTrue(CC.is_word_mode(words))
        self.assertEqual(CC.phrasing_findings(words), [])
        c = caps(("protein matters most", 0.0, 1.0), ("really", 1.05, 1.3), ("for muscle growth", 1.35, 2.0))
        self.assertEqual(CC.phrasing_findings(c, mode="word"), [])

    def test_hidden_captions_ignored(self):
        c = caps(("the ideal amount of", 0.0, 1.0), ("protein every day", 1.1, 2.0))
        c[0]["hidden"] = True
        self.assertEqual(CC.phrasing_findings(c), [])


class Shapes(unittest.TestCase):
    def test_captions_list(self):
        raw = {"caption_mode": "word", "captions": [{"text": "b", "t0": 1, "t1": 2}, {"text": "a", "t0": 0, "t1": 1},
                                                    {"text": "x", "t0": 2, "t1": 3, "hidden": True}]}
        got, mode = CC.captions_from_layout(raw)
        self.assertEqual([c["text"] for c in got], ["a", "b"])
        self.assertEqual(mode, "word")

    def test_beats_boxes_and_plain_list(self):
        beats = {"beats": [{"t0": 0, "t1": 3, "boxes": [
            {"kind": "caption", "x": 0, "y": 0, "w": 9, "h": 9, "t0": 0, "t1": 1, "text": "hello there"},
            {"kind": "text", "t0": 0, "t1": 3, "text": "HEADLINE"},
            {"type": "caption_pill", "t0": 1, "t1": 2, "text": "second one"}]},
            {"t0": 3, "t1": 4, "boxes": [{"kind": "caption", "t0": 0, "t1": 1, "text": "hello there"}]}]}
        got, _ = CC.captions_from_layout(beats)
        self.assertEqual([c["text"] for c in got], ["hello there", "second one"])   # duplicate across beats dropped
        plain = [{"role": "caption", "start": 0.5, "end": 1.0, "text": "one"}, {"role": "face", "t0": 0, "t1": 1}]
        self.assertEqual(CC.captions_from_layout(plain)[0], [{"text": "one", "t0": 0.5, "t1": 1.0}])
        self.assertIsNone(CC.captions_from_layout({"boxes": [{"kind": "text", "t0": 0, "t1": 1, "text": "x"}]})[0])


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, data):
        (self.tmp / "layout_boxes.json").write_text(json.dumps(data))

    def test_skipped_without_layout_or_captions(self):
        r = CC.check(self.tmp)
        self.assertTrue(r["pass"] and r["skipped"])
        self.write({"boxes": []})
        self.assertTrue(CC.check(self.tmp)["skipped"])

    def test_pass_and_fail_reports(self):
        self.write({"captions": [{"text": "the ideal amount of", "t0": 0, "t1": 1},
                                 {"text": "protein every day", "t0": 1.1, "t1": 2}]})
        r = CC.check(self.tmp)
        self.assertEqual((r["name"], r["pass"], r["label"]), ("caption_phrasing", False, CC.LABEL))
        self.assertIn("1 caption break problem: mid-phrase break", r["detail"])
        rep = json.loads((self.tmp / "qa" / "capcheck.json").read_text())
        self.assertFalse(rep["pass"])
        out = self.tmp / "elsewhere.json"
        self.write({"captions": [{"text": "all good here.", "t0": 0, "t1": 1}]})
        self.assertTrue(CC.run(self.tmp, out)["pass"])
        self.assertTrue(json.loads(out.read_text())["pass"])


if __name__ == "__main__":
    unittest.main()
