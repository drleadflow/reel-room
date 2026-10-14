"""rr_autoedit: the `reel demo` first-pass edit from the user's own words (no Claude, no key)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "reel" / "engine"))
sys.path.insert(0, str(ROOT / "skills" / "reel" / "tools"))
import plan_schema as PS  # noqa: E402
import rr_autoedit as AE  # noqa: E402


def words(text, t0, gap=0.25):
    out, t = [], t0
    for w in text.split():
        out.append({"w": w, "s": round(t, 2), "e": round(t + gap, 2), "p": 0.9})
        t += gap + 0.05
    return out


class AutoEdit(unittest.TestCase):
    def setUp(self):
        self.words = (words("If you want better sleep tonight, here are 3 things I would do.", 0.5)
                      + words("Number 1, I would stop", 5.0)
                      + words("Number 1, I would stop caffeine after 2 PM.", 7.5)
                      + words("Keep your bedroom cool, around 65 degrees.", 11.5)
                      + words("Save this and try it tonight.", 15.0))

    def test_pauses_split_and_retake_dropped(self):
        edl = AE.edl_from(self.words)
        lines = [s["line"] for s in edl]
        self.assertEqual(len(edl), 4)
        self.assertTrue(lines[1].startswith("Number 1, I would stop caffeine"))     # the earlier take is gone
        self.assertEqual([s["mode"] for s in edl], ["split", "full", "split", "full"])

    def test_plan_is_valid_and_uses_only_spoken_words(self):
        edl = AE.edl_from(self.words)
        plan = AE.plan_from(edl, "split-deck")
        lines = {s["id"]: s["line"] for s in edl}
        self.assertIsNone(PS.check_reel_plan(plan, lines))
        for b in plan["beats"]:
            if b["component"] != "none":
                self.assertIsNone(PS.invented(b["on_screen_text"], lines[b["id"]]))
        self.assertTrue(plan["title"].isupper() and len(plan["title"]) <= PS.MAX_TITLE)

    def test_hero_lands_on_a_number_line(self):
        plan = AE.plan_from(AE.edl_from(self.words), "split-deck")
        self.assertIn(plan["hero_moments"][0]["anchor_word"], {"3", "1", "65"})


if __name__ == "__main__":
    unittest.main()
