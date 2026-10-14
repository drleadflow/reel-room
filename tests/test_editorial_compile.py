"""editorial-ui adapter, everyday editorial beats, cut-out cache and parallel bake helpers (no network, no render):
python -m unittest tests/test_editorial_compile.py (from the repo root)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / "skills" / "reel"
sys.path.insert(0, str(SK / "engine"))
sys.path.append(str(SK / "templates" / "kit"))

import beat_schema as BS  # noqa: E402
import cutout_cache as CC  # noqa: E402
from compile import editorial_ui as EU  # noqa: E402
from compile import everyday as E  # noqa: E402
from compile import split_deck  # noqa: E402

LINE = "And you can do it now because Claude can turn your boring yaps into fully edited videos."
BRAND = {"colors": {"bg": "#F4F1EC", "ink": "#0C0C0F", "accent": "#1B8A68", "highlight": "#FAE67A",
                    "alert": "#C8323F"}, "fonts": {"display": "Inter Tight", "body": "Inter"}, "handle": "x"}


class BeatSchemaTests(unittest.TestCase):
    def test_spoken_fill_passes(self):
        self.assertIsNone(BS.validate("ed-number", {"value": "100%", "context": "edited with", "land": "@edited"},
                                      "It's 100% edited with Claude."))

    def test_invented_number_and_words_fail(self):
        self.assertIn("never said", BS.validate("ed-number", {"value": "200%"}, "It's 100% edited with Claude."))
        self.assertIn("invents", BS.validate("ed-kicker", {"kicker": "brand new words", "text": "Claude"},
                                             "It's 100% edited with Claude."))

    def test_anchor_and_fields(self):
        self.assertIn("not a word", BS.validate("ed-headline", {"text": "Claude", "land": "@banana"},
                                                "It's 100% edited with Claude."))
        self.assertIn("unknown field", BS.validate("ed-headline", {"text": "Claude", "colour": "red"}, "Claude"))
        self.assertIn("needs", BS.validate("ed-contrast", {"left": "boring yaps"}, LINE))


class EverydayTests(unittest.TestCase):
    def test_kicker_and_sub_are_verbatim(self):
        self.assertEqual(E.kicker_of("STAND OUT", "So if you want to really stand out, you have to"), "want to really")
        self.assertEqual(E.sub_of("Claude or ChatGPT", "all you need is Claude or ChatGPT and the right skill."),
                         "and the right skill")
        self.assertIsNone(E.sub_of("stand out", "you want to really stand out, you have to"))

    def test_build_each_kind(self):
        word = E.build({"kind": "word", "text": "STAND OUT", "anchor": "@stand"},
                       "So if you want to really stand out, you have to")
        self.assertEqual(word[0], "ed-kicker")
        flow = E.build({"kind": "flow", "left": "boring yaps", "arrow": "→", "right": "edited videos",
                        "anchor": "@turn"}, LINE)
        self.assertEqual((flow[0], flow[1]["strike_at"], flow[1]["land"]), ("ed-contrast", "@edited", "@edited"))
        stat = E.build({"kind": "stat", "value": "100%", "label": "", "anchor": "@100%"}, "It's 100% edited with Claude.")
        self.assertEqual(stat[0], "ed-number")
        lst = E.build({"kind": "list", "items": ["graphics", "animations"], "ticks": ["@graphics", "@animations"]},
                      "The graphics, the animations.")
        self.assertEqual(lst[1]["ticks"], ["@graphics", "@animations"])

    def test_rotation_and_number_slam(self):
        shot = {"kind": "word", "text": "STAND OUT", "anchor": "@stand"}
        line = "So if you want to really stand out, you have to"
        self.assertEqual(E.build(shot, line)[0], "ed-kicker")
        self.assertEqual(E.build(shot, line, avoid="ed-kicker")[0], "ed-headline")
        num = E.build({"kind": "word", "text": "100% edited", "anchor": "@edited"}, "It's 100% edited with Claude.")
        self.assertEqual((num[0], num[1]["value"]), ("ed-number", "100%"))

    def test_invalid_fill_returns_none(self):
        self.assertIsNone(E.build({"kind": "stat", "value": "300%", "label": "", "anchor": None}, "It's 100% done."))

    def test_split_deck_uses_everyday_beats(self):
        mode, top = split_deck.top_for({"kind": "list", "items": ["graphics", "animations"], "ticks": [None, None],
                                        "anchor": "@graphics"}, "The graphics, the animations.", "cream")
        self.assertEqual((mode, top["insert"], top["args"]["comp"], top["args"]["tone"]),
                         ("split", "beat", "ed-checklist", "cream"))
        calm = split_deck._calm({"kind": "word"}, {"text": "specific skill", "land": "@skill", "tone": "dark"},
                                "And that's why I created a specific skill")
        self.assertEqual(calm["args"]["comp"], "ed-kicker")


def shots_fixture():
    sh = lambda kind, sec, **kw: {"kind": kind, "section": sec, "purpose": "explain", **kw}  # noqa: E731
    return [("a", sh("word", "s1", text="Video editors", anchor="@video")),
            ("b", sh("hero", "s1", hero_id="word-stamp", comp="word-stamp", args={"word": "COOKED", "at": "@cooked"},
                     anchor="@cooked")),
            ("c", sh("word", "s2", text="STAND OUT", anchor="@stand")),
            ("d", sh("word", "s2", text="plummeted", anchor="@plummeted")),
            ("e", sh("none", "s3"))]


LINES = {"a": "Video editors are", "b": "completely and utterly cooked.",
         "c": "So if you want to really stand out, you have to", "d": "plummeted.", "e": "Look at the sunset."}
WINS = {"a": (0.0, 1.0), "b": (1.0, 3.0), "c": (3.0, 6.0), "d": (6.0, 6.5), "e": (6.5, 9.0)}


class EditorialAdapterTests(unittest.TestCase):
    def test_sets_hook_and_long_words_only(self):
        sets = EU.pick_sets(shots_fixture(), WINS)
        self.assertIn(0, sets)
        self.assertIn(2, sets)
        self.assertNotIn(3, sets)            # 0.5 s cut: too short for the colour set

    def test_beats_and_cutout_need(self):
        beats, need, _notes = EU.editorial_beats(shots_fixture(), LINES, "Video editors are cooked", WINS)
        self.assertEqual(beats["a"]["headlines"][0]["text"], "VIDEO EDITORS|_are cooked_")
        self.assertEqual(beats["c"]["scene"], "set")
        self.assertNotEqual(beats["a"]["set"], beats["c"]["set"])      # consecutive sets change colour
        hero = beats["b"]["cards"][0]
        self.assertEqual((hero["kind"], hero["matte"]), ("hero", True))
        self.assertIn([0, 30], need)                                      # the hook's set frames
        self.assertTrue(any(a == 30 and b >= 90 for a, b in need))        # the matte hero span (+ pad)
        self.assertEqual(beats["d"]["cards"], [])                         # 0.5 s cut: a card would only flash

    def test_headline_lines_and_caps(self):
        self.assertEqual(EU.headline_text({"text": "visual palette"}, "a visual palette so you"), "VISUAL|PALETTE")
        many = [(str(i), {"kind": "hero", "hero_id": "word-stamp", "anchor": "@w", "args": {}, "comp": "word-stamp"})
                for i in range(7)]
        self.assertEqual(sum(1 for _, s in EU.cap_heroes(many) if s["kind"] == "hero"), EU.HERO_CAP)
        off = EU.cap_heroes([("x", {"kind": "hero", "hero_id": "nle-timeline", "anchor": "@claude", "args": {},
                                    "comp": "nle-timeline"})])
        self.assertEqual((off[0][1]["kind"], off[0][1]["text"]), ("word", "claude"))

    def test_palette_from_brand(self):
        pal = EU.palette(BRAND)
        self.assertEqual(sorted(pal), ["accent", "cream", "dark", "tan"])
        self.assertNotEqual(pal["accent"]["plate"], pal["dark"]["plate"])     # accent set: toned brand accent


class CutoutCacheTests(unittest.TestCase):
    def test_need_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            (proj / "work").mkdir()
            CC.write_need(proj, [[10, 13], [0, 2], [5, 5]])
            self.assertEqual(CC.read_need(proj / "work" / "cutout_need.json"), {0, 1, 10, 11, 12})
            self.assertIsNone(CC.read_need(proj / "work" / "nope.json"))
            (proj / "m00001.png").write_bytes(b"x")
            self.assertEqual(CC.missing(proj, [0, 1, 2]), [0, 2])
            self.assertEqual(CC.span_rel(3, 40), "assets/matte/span_00003_00040.webm")


class TemplateHelperTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SK / "templates" / "editorial-ui"))

    def test_bake_spans_balance_and_cover(self):
        import bake_par
        segs = [{"f0": 0, "f1": 60, "scene": "set"}, {"f0": 60, "f1": 600, "scene": "room"},
                {"f0": 600, "f1": 700, "scene": "set"}, {"f0": 700, "f1": 800, "scene": "takeover"}]
        sp = bake_par.spans(SimpleNamespace(segs=segs, frames=800), 4)
        self.assertEqual(sp[0][0], 0)
        self.assertEqual(sp[-1][1], 800)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(sp, sp[1:])))
        self.assertFalse(any(700 < a < 800 for a, _ in sp))             # a takeover cut is never split

    def test_behind_keeps_stamp_in_safe_zone(self):
        import kitcards
        html = ('<div class="ws-stack" style="top:194px;left:80px"><div class="ws-w" style="font-size:380px" '
                'data-box="text" data-t0="1">E</div>')
        out = kitcards.behind(html, (620, 600, 250))
        self.assertIn('data-box="behind"', out)
        self.assertIn("top:228px", out)
        self.assertIn('data-fit="796,90"', out)


class KitBeatTests(unittest.TestCase):
    def test_beats_build_in_both_layouts(self):
        import rrkit
        words = [{"text": "turn", "start": 1.0, "end": 1.2}, {"text": "edited", "start": 1.6, "end": 1.9}]
        k = rrkit.Kit(BRAND, words, base=0.0, end=4.0)
        k.default_until = 4.0
        for comp, a in [("ed-headline", {"text": "Stand out", "sub": "your own visual"}),
                        ("ed-number", {"value": "100%", "context": "edited with"}),
                        ("ed-checklist", {"items": ["graphics", "animations"]}),
                        ("ed-contrast", {"left": "boring yaps", "right": "edited videos", "land": "@edited"}),
                        ("ed-kicker", {"kicker": "highly visual", "text": "cinematic"})]:
            for lay in ("split", "full"):
                p = rrkit.build(k, comp, layout=lay, area=[900, 1270] if lay == "full" else None, **a)
                self.assertIn('data-box="', p.html)
                self.assertNotIn("—", p.html)
                self.assertLessEqual(p.meta["times"]["in"] + 0.1, p.meta["times"]["out"])


if __name__ == "__main__":
    unittest.main()
