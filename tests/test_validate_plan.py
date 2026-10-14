"""validate_plan.py: a hand-written plan (no API key) is checked like the planner's own and saved as plan_fast.json."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "skills" / "reel" / "engine"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ENGINE))
import validate_plan as VP  # noqa: E402


class ValidatePlan(unittest.TestCase):
    def setUp(self):
        self.proj = Path(tempfile.mkdtemp())
        shutil.copyfile(FIX / "demo_edl.json", self.proj / "edl.json")
        self.plan = json.loads((FIX / "demo_plan.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.proj, ignore_errors=True)

    def run_plan(self, plan):
        (self.proj / "draft.json").write_text(json.dumps(plan))
        return VP.main([str(self.proj), "draft.json"])

    def test_demo_plan_is_valid_and_saved_in_planner_shape(self):
        self.assertEqual(self.run_plan(self.plan), 0)
        out = json.loads((self.proj / "work" / "plan_fast.json").read_text())
        self.assertEqual([b["id"] for b in out["beats"]], [s["id"] for s in json.loads(
            (self.proj / "edl.json").read_text())])
        self.assertEqual(out["hook"]["pick"], "hook")
        self.assertTrue(all(b["hero"] for b in out["beats"] if b["id"] in ("cooked", "money")))

    def test_library_heroes_with_args_become_claude_picks(self):
        self.assertEqual(self.run_plan(self.plan), 0)
        todo = json.loads((self.proj / "work" / "hero_todo.json").read_text())
        picks = {(t["line_id"], t["library"]["hero"]) for t in todo if t["style"] == "split-deck"}
        self.assertEqual(picks, {("cooked", "fire-timeline"), ("money", "money-counter")})
        self.assertTrue(all(t["library"]["source"] == "claude" for t in todo))

    def test_invented_number_is_rejected(self):
        bad = json.loads(json.dumps(self.plan))
        bad["beats"][1]["on_screen_text"] = "8 hours"
        self.assertEqual(self.run_plan(bad), 1)
        self.assertFalse((self.proj / "work" / "plan_fast.json").exists())

    def test_missing_beat_is_reported(self):
        bad = json.loads(json.dumps(self.plan))
        bad["beats"] = bad["beats"][:-1]
        errs = VP.check(bad, VP.load_lines(self.proj))
        self.assertTrue(any("missing" in e for e in errs))

    def test_bad_hero_args_are_rejected(self):
        bad = json.loads(json.dumps(self.plan))
        bad["hero_moments"][1]["args"]["steps"] = [["75", "@75"]]
        self.assertEqual(self.run_plan(bad), 1)


if __name__ == "__main__":
    unittest.main()
