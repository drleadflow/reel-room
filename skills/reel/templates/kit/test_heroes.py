"""Hero library tests (no render): registration, every hero builds in each layout it claims, seek-safe JS, entrance
eases, no em dashes, readable boxes inside the safe zone, the hero_scale width, the typed contract validator, and
the compiler's rich top slot (colour sets per section, hero spans).

  PY templates/kit/test_heroes.py
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SK, "engine"))
import rrkit  # noqa: E402
import hero_schema as HS  # noqa: E402
import qa_motion  # noqa: E402

LINE = "the barrier to entry to creating cinematic videos has just plummeted from 15 to 60 in 2019"
WORDS = [{"text": w, "start": round(i * 0.32, 2), "end": round(i * 0.32 + 0.26, 2)} for i, w in enumerate(LINE.split())]
IMG = ["assets/hero/a.jpg", "assets/hero/b.jpg", "assets/hero/c.jpg", "assets/hero/d.jpg", "assets/hero/e.jpg"]
FILL = {
    "title-stamp": dict(text="barrier to entry", sub="plummeted", neq=True, land="@barrier", sub_at="@plummeted"),
    "word-stamp": dict(word="plummeted", setup="the barrier to entry", strike=True, at="@plummeted"),
    "magazine-cover": dict(mast="cinematic", lines=["the barrier", "to entry", "has just", "plummeted"], sticker="60",
                           lines_at=["@barrier", "@has"], sticker_at="@60"),
    "money-counter": dict(steps=[("15", "@15"), ("60", "@60")], prefix="$", unit="billion", label="cinematic videos"),
    "cycle-chart": dict(shape="drop", labels=["barrier to entry"], marks=["@barrier"], stamp="plummeted",
                        stamp_at="@plummeted", stopwatch=True),
    "evidence-hero": dict(kind="bar", citation="Lei et al., Sci Rep 2017", labels=["0 h", "24 h"],
                          series=[{"name": "a", "values": [100, 66]}, {"name": "b", "values": [100, 82]}], stat="60",
                          stat_label="cinematic videos", stamp="@60", highlight=[1, 1], highlight_at="@2019"),
    "nle-timeline": dict(title="cinematic videos", land="@plummeted"),
    "video-card": dict(title="creating cinematic videos", chapters=["barrier", "entry", "plummeted"],
                       play_at="@creating", chapter_at=["@cinematic", "@has", "@plummeted"]),
    "palette-fan": dict(items=IMG, label="cinematic videos", fan_at="@creating", pick_at="@plummeted"),
    "grid-collapse": dict(pop_at="@entry", cue="@plummeted", tiles=IMG),
    "reel-orbit": dict(media=IMG),
    "fire-timeline": dict(title="cinematic videos", ignite="@has", burn="@plummeted"),
}


def build(hid, layout):
    k = rrkit.Kit(None, WORDS)
    args = dict(FILL[hid], until=7.5)
    if layout != "split":
        args["layout"] = layout
    if layout in ("card", "stage", "full"):
        args.setdefault("area", [240, 880])
    import inspect
    params = inspect.signature(HS.HEROES[hid]["fn"]).parameters
    return rrkit.build(k, hid, **{a: v for a, v in args.items() if a in params})


class Heroes(unittest.TestCase):
    def test_registered(self):
        self.assertEqual(len(HS.HEROES), 12)
        for hid, c in HS.HEROES.items():
            self.assertIn(hid, rrkit.COMPONENTS)
            self.assertTrue(rrkit.COMPONENTS[hid]["hero"])
            self.assertTrue(hasattr(rrkit.Kit, c["method"]))
            self.assertTrue(c["fits"] and c["layouts"] and c["say"] and c["what"])
            self.assertIn(hid, FILL, "every hero needs a test fill")

    def test_builds_everywhere(self):
        for hid, c in HS.HEROES.items():
            for layout in c["layouts"]:
                if layout in ("overlay", "media"):
                    continue
                with self.subTest(hero=hid, layout=layout):
                    p = build(hid, layout)
                    self.assertEqual(p.comp, hid)
                    self.assertIn("data-hero", p.html)
                    self.assertLess(p.t0, p.t1)
                    self.assertTrue(p.events("light"), "a hero emits light SFX cue points")
                    self.assertTrue(all(p.t0 - 0.7 <= e["t"] <= p.t1 + 0.1 for e in p.sfx))

    def test_seek_safe_and_eases(self):
        for hid, c in HS.HEROES.items():
            p = build(hid, c["layouts"][0])
            js = "\n".join(p.js)
            with self.subTest(hero=hid):
                self.assertNotIn("Math.random", js)
                self.assertNotIn("Date.now", js)
                self.assertNotIn("—", p.html + js, "no em dashes")
                lint = qa_motion.ease_lint(f"<div id='{p.id}' data-hero></div><script>{js}</script>")
                self.assertEqual(lint["bad"], [], "no entrance on a linear or ease-in curve")
                self.assertEqual(lint["opacity_only_hero"], [])

    def test_safe_zone_and_scale(self):
        for hid, c in HS.HEROES.items():
            p = build(hid, c["layouts"][0])
            x, y, w, h = p.meta["box"]
            with self.subTest(hero=hid):
                self.assertGreaterEqual(w, 0.6 * 1080, "hero_scale: at least 60 % of the frame width")
                if c["layouts"][0] == "split":
                    self.assertGreaterEqual(y, 220)
                    self.assertLessEqual(y + h, 960)
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w, 1080)

    def test_readable_boxes_in_band(self):
        """Split heroes: every readable text element sits inside the panel's safe band (style top values)."""
        for hid, c in HS.HEROES.items():
            if c["layouts"][0] != "split":
                continue
            p = build(hid, "split")
            tops = [int(t) for t in re.findall(r'class="[^"]*"[^>]*style="[^"]*top:(\d+)px[^"]*"[^>]*data-box="text"', p.html)]
            with self.subTest(hero=hid):
                self.assertTrue(all(220 <= t <= 940 for t in tops), tops)


class Contract(unittest.TestCase):
    def test_good_fill_passes(self):
        self.assertIsNone(HS.validate("cycle-chart", {"shape": "drop", "labels": ["barrier to entry"],
                                                      "marks": ["@barrier"], "stamp": "plummeted"}, LINE))
        self.assertIsNone(HS.validate("money-counter", {"steps": [["15", "@15"], ["60", "@60"]], "prefix": "$"}, LINE))

    def test_invented_words_and_numbers(self):
        self.assertIn("invents", HS.validate("title-stamp", {"text": "editors are finished forever"}, LINE))
        self.assertIn("never said", HS.validate("money-counter", {"steps": [["99", "@15"]]}, LINE))

    def test_anchor_must_be_in_line(self):
        self.assertIn("not a word", HS.validate("title-stamp", {"text": "cinematic videos", "land": "@banana"}, LINE))

    def test_types_and_limits(self):
        self.assertIn("em dash", HS.validate("title-stamp", {"text": "videos — plummeted"}, LINE))
        self.assertIn("over 28", HS.validate("title-stamp", {"text": "x" * 40}, LINE))
        self.assertIn("unknown field", HS.validate("title-stamp", {"text": "videos", "colour": "red"}, LINE))
        self.assertIn("colour set", HS.validate("title-stamp", {"text": "videos", "tone": "neon"}, LINE))
        self.assertIn("needs", HS.validate("video-card", {"title": "cinematic videos"}, LINE))
        self.assertIn("unknown field", HS.validate("title-stamp", {"text": "videos", "until": "@has"}, LINE))

    def test_citation_needs_project_sources(self):
        fill = {"kind": "bar", "citation": "Lei et al., Sci Rep 2017", "labels": ["0 h", "24 h"],
                "series": [{"name": "x", "values": [15, 60]}]}
        self.assertIn("no source", HS.validate("evidence-hero", fill, LINE))
        self.assertIsNone(HS.validate("evidence-hero", fill, LINE, sources="Lei et al., Sci Rep 2017. Fig 3: wound area at 0 h and 24 h."))

    def test_catalog_and_validator(self):
        txt = HS.catalog_text()
        for hid in HS.HEROES:
            self.assertIn(f"- {hid}:", txt)
        check = HS.validator(["title-stamp"], LINE)
        self.assertIsNone(check({"hero": "none"}))
        self.assertIn("one of", check({"hero": "reel-orbit", "args": {}}))


class RichTop(unittest.TestCase):
    def test_tones_and_spans(self):
        sys.path.insert(0, os.path.join(SK, "engine"))
        from compile import rich as R
        shots = [("a", {"kind": "word", "section": "s1"}), ("b", {"kind": "none", "section": "s2"}),
                 ("c", {"kind": "none", "section": "s2"}), ("d", {"kind": "hero", "hero_id": "cycle-chart", "section": "s2"})]
        tones = R.section_tones(shots)
        self.assertEqual(tones, {"s1": "dark", "s2": "cream"})
        rows = [{"id": "a", "mode": "split", "top": {}}, {"id": "b", "mode": "full", "top": None},
                {"id": "c", "mode": "full", "top": None}, {"id": "d", "mode": "split", "top": {"insert": "hero"}}]
        wins = {"a": (0, 1), "b": (1, 2.2), "c": (2.2, 3.0), "d": (3.0, 3.5)}
        out = R.extend_spans(rows, shots, wins)
        self.assertEqual(out[1]["top"], {"insert": "hero"})
        self.assertEqual([r["top"] for r in out[2:]], ["same", "same"])
        self.assertTrue(all(r["mode"] == "split" for r in out[1:]))


class Caps(unittest.TestCase):
    def test_title_stamp_cap(self):
        from compile import rich as R
        stamp = lambda t: {"insert": "hero", "args": {"comp": "title-stamp", "text": t, "tone": "dark"}}  # noqa: E731
        rows = [{"id": f"s{i}", "mode": "split", "top": stamp(f"word {i}")} for i in range(7)]
        shots = [(f"s{i}", {"kind": "word", "section": "a", "purpose": "proof" if i == 5 else "explain",
                            "hero": i == 3}) for i in range(7)]
        out = R.cap_title_stamps(rows, shots, lambda shot, args: "calm")
        kept = [i for i, r in enumerate(out) if r["top"] != "calm"]
        self.assertEqual(len(kept), R.TITLE_STAMP_CAP)
        self.assertTrue({0, 3, 5} <= set(kept), "the hook, the hero beat and the proof line keep their stamps")

    def test_hero_cap_is_five(self):
        import plan_schema as PS
        lines = {f"l{i}": f"line number {i} with a payoff word" for i in range(6)}
        hero = lambda i: {"line_id": f"l{i}", "anchor_word": "payoff", "idea": "a concrete hero idea for this line"}  # noqa
        self.assertIsNone(PS.check_heroes([hero(i) for i in range(5)], lines))
        self.assertIn("1 to 5", PS.check_heroes([hero(i) for i in range(6)], lines))


if __name__ == "__main__":
    unittest.main(verbosity=1)
