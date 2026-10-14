"""judge.py verdict validation (no network, no ffmpeg): python -m unittest tests/test_judge.py (from the repo root)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "reel" / "engine"))

import judge as J  # noqa: E402

GOOD = {k: 8 for k in J.CRITERIA}


class VerdictTests(unittest.TestCase):
    def test_clean_pass(self):
        self.assertIsNone(J.check_verdict({"scores": dict(GOOD), "issues": []}))

    def test_missing_criterion_rejected(self):
        scores = dict(GOOD)
        scores.pop("premium")
        self.assertIn("exactly these keys", J.check_verdict({"scores": scores, "issues": []}))

    def test_out_of_range_rejected(self):
        self.assertIn("0 to 10", J.check_verdict({"scores": {**GOOD, "motion": 11}, "issues": []}))

    def test_low_score_needs_issue(self):
        err = J.check_verdict({"scores": {**GOOD, "readable": 5}, "issues": []})
        self.assertIn("readable", err)

    def test_low_score_with_issue_passes_validation(self):
        issue = {"t": 1.2, "criterion": "readable", "issue": "title clipped", "fix": "shrink to 90%"}
        self.assertIsNone(J.check_verdict({"scores": {**GOOD, "readable": 5}, "issues": [issue]}))

    def test_issue_needs_timestamp(self):
        issue = {"criterion": "motion", "issue": "stutter", "fix": "x"}
        self.assertIn("t (seconds)", J.check_verdict({"scores": dict(GOOD), "issues": [issue]}))


class CompareTests(unittest.TestCase):
    def test_compare_ok(self):
        self.assertIsNone(J.check_compare({"compare": {k: "same" for k in J.CRITERIA}, "issues": []}))

    def test_worse_needs_issue(self):
        comp = {**{k: "same" for k in J.CRITERIA}, "premium": "worse"}
        self.assertIn("premium", J.check_compare({"compare": comp, "issues": []}))

    def test_bad_value(self):
        comp = {**{k: "same" for k in J.CRITERIA}, "motion": "meh"}
        self.assertIn("one of", J.check_compare({"compare": comp, "issues": []}))


if __name__ == "__main__":
    unittest.main()
