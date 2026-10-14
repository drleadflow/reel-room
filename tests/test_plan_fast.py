"""plan_fast / plan_schema unit tests (no network): python -m unittest tests/test_plan_fast.py (from the repo root)."""
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "reel" / "engine"))

import llm_router as LR  # noqa: E402
import plan_fast as PF  # noqa: E402
import plan_schema as PS  # noqa: E402

LINES = {"a": "Video editors are cooked.", "b": "It's 100% edited with Claude.", "c": "Comment the word EDIT."}
GOOD_PLAN = {
    "title": "Video editors are cooked",
    "hook_id": "a",
    "sections": [{"name": "hook", "style": "editorial-ui", "purpose": "hook", "line_ids": ["a"]},
                 {"name": "proof", "style": "floating-cards", "purpose": "proof", "line_ids": ["b", "c"]}],
    "hero_moments": [{"line_id": "a", "anchor_word": "cooked", "idea": "An editing timeline bursts into flames."}],
}


class SchemaTests(unittest.TestCase):
    def test_good_plan_passes(self):
        self.assertIsNone(PS.check_reel_plan(GOOD_PLAN, LINES))

    def test_sections_must_cover_in_order(self):
        bad = {**GOOD_PLAN, "sections": [{"name": "x", "style": "clean-talk", "purpose": "hook", "line_ids": ["b", "a"]}]}
        self.assertIn("transcript order", PS.check_reel_plan(bad, LINES))

    def test_bad_style_rejected(self):
        bad = {**GOOD_PLAN, "sections": [{**GOOD_PLAN["sections"][0], "style": "vaporwave"}, GOOD_PLAN["sections"][1]]}
        self.assertIn("bad style", PS.check_reel_plan(bad, LINES))

    def test_hero_anchor_must_be_in_line(self):
        bad = {**GOOD_PLAN, "hero_moments": [{**GOOD_PLAN["hero_moments"][0], "anchor_word": "fire"}]}
        self.assertIn("anchor_word", PS.check_reel_plan(bad, LINES))

    def test_em_dash_title_rejected(self):
        self.assertIn("em dash", PS.check_reel_plan({**GOOD_PLAN, "title": "Cooked — really"}, LINES))

    def test_beat_rules(self):
        check = PS.check_beat(LINES["b"])
        self.assertIsNone(check({"component": "odometer", "on_screen_text": "100%", "anchor_word": "100%"}))
        self.assertIn("anchor_word", check({"component": "odometer", "on_screen_text": "", "anchor_word": "zero"}))
        self.assertIn("component", check({"component": "confetti", "on_screen_text": "", "anchor_word": "100%"}))
        self.assertIn("chars", check({"component": "none", "on_screen_text": "x" * 40, "anchor_word": ""}))


class InventionTests(unittest.TestCase):
    def test_made_up_number_rejected(self):
        check = PS.check_beat("The barrier to entry has plummeted.")
        self.assertIn("never said", check({"component": "label-pill", "on_screen_text": "Barrier: 100% to 5%",
                                           "anchor_word": "barrier"}))

    def test_made_up_words_rejected(self):
        check = PS.check_beat("All you need is Claude or ChatGPT and the right skill.")
        self.assertIn("invents", check({"component": "typer", "on_screen_text": "Build a full app",
                                        "anchor_word": "Claude"}))

    def test_own_words_and_neighbours_pass(self):
        check = PS.check_beat("It's 100% edited with Claude.", context="I didn't edit a single thing.")
        self.assertIsNone(check({"component": "odometer", "on_screen_text": "100% EDITED", "anchor_word": "100%"}))
        self.assertIsNone(check({"component": "label-pill", "on_screen_text": "Single thing", "anchor_word": "Claude"}))


class RouterTests(unittest.TestCase):
    def test_escalates_with_error_feedback(self):
        replies = [{"routed": "cheap", "secs": 0.1, "cost": 0, "data": {"best_id": "zzz"}},
                   {"routed": "strong", "secs": 0.2, "cost": 0, "data": {"best_id": "a"}}]
        prompts = []

        def fake(model, prompt, max_tokens, media=None):
            prompts.append(prompt)
            return replies[len(prompts) - 1]
        with mock.patch.object(LR, "call_json", side_effect=fake):
            res = LR.typed("pick", PS.check_vote(list(LINES)), ("cheap", "strong"))
        self.assertEqual(res["data"], {"best_id": "a"})
        self.assertEqual(len(res["attempts"]), 2)
        self.assertIn("rejected", prompts[1])

    def test_all_fail_returns_none(self):
        with mock.patch.object(LR, "call_json", side_effect=ValueError("no JSON")):
            res = LR.typed("pick", PS.check_vote(list(LINES)), ("a", "b"))
        self.assertIsNone(res["data"])
        self.assertEqual(len(res["attempts"]), 2)


class StageBTests(unittest.TestCase):
    def test_heroes_skip_jev_and_sections_carry_style(self):
        beat = {"data": {"component": "odometer", "on_screen_text": "100%", "anchor_word": "100%", "why": "x"},
                "attempts": [{"model": "jev", "secs": 0.1, "cost": 0, "error": None}]}
        with mock.patch.object(LR, "typed", return_value=beat) as typed, ThreadPoolExecutor(4) as pool:
            beats = PF.stage_b(pool, LINES, GOOD_PLAN, "comps")
        self.assertEqual(typed.call_count, 2)  # line "a" is a hero moment
        self.assertEqual(beats[0]["component"], "custom")
        self.assertEqual(beats[1]["style"], "floating-cards")

    def test_hook_verdict_majority(self):
        votes = [{"data": {"best_id": "b"}}, {"data": {"best_id": "a"}}, {"data": None}]
        v = PF.hook_verdict(GOOD_PLAN, votes)
        self.assertEqual(v["pick"], "a")
        self.assertEqual(v["votes"]["a"], 2)


if __name__ == "__main__":
    unittest.main()
