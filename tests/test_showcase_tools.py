"""showcase.py + aroll_fix.py unit tests (no render): python -m unittest tests/test_showcase_tools.py (from the repo root)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import aroll_fix as AF  # noqa: E402
import showcase as SC  # noqa: E402

CATALOG = {
    "version": 2,
    "styles": [
        {"id": "split-deck", "name": "Split deck", "examples": [
            {"title": "T", "person": "P", "reel": "vaping", "src": "styles/showcase/a.mp4", "poster": "styles/showcase/a.jpg",
             "seconds": 81.0, "kind": "showcase"}]},
        {"id": "clean-talk", "name": "Clean Talk"},
    ],
    "examples_offcatalog": [{"title": "T", "person": "Q", "reel": "vaping", "style_label": "Own look, re-cut",
                             "src": "styles/showcase/b.mp4", "poster": "styles/showcase/b.jpg", "seconds": 83.0,
                             "kind": "showcase"}],
}


class ShowcaseTests(unittest.TestCase):
    def test_bitrate_fits_cap(self):
        for dur in (30, 67, 81, 120):
            kbps = SC.video_kbps(dur, 12)
            mb = (kbps + SC.AUDIO_KBPS) * dur / 8 / 1024
            self.assertLess(mb, 12)
        self.assertEqual(SC.video_kbps(5, 12), SC.MAX_VIDEO_KBPS)   # short clips are capped, not huge
        with self.assertRaises(ValueError):
            SC.video_kbps(0, 12)

    def test_iter_examples_includes_offcatalog(self):
        got = list(SC.iter_examples(CATALOG))
        self.assertEqual([s for s, _ in got], ["split-deck", None])

    def test_examples_doc_swaps_assets_and_reports_missing(self):
        assets = {"styles/showcase/a.mp4": "/_blob/1", "styles/showcase/a.jpg": "/_blob/2"}
        doc = SC.examples_doc(CATALOG, assets)
        self.assertEqual(len(doc["items"]), 1)
        item = doc["items"][0]
        self.assertEqual((item["style"], item["src"], item["poster"], item["preview_kind"]),
                         ("split-deck", "/_blob/1", "/_blob/2", "video"))
        self.assertEqual(doc["missing"], ["styles/showcase/b.mp4"])
        assets.update({"styles/showcase/b.mp4": "/_blob/3", "styles/showcase/b.jpg": "/_blob/4"})
        off = SC.examples_doc(CATALOG, assets)["items"][1]
        self.assertIsNone(off["style"])
        self.assertEqual(off["style_label"], "Own look, re-cut")

    def test_faststart_detection(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = Path(d) / "g.mp4", Path(d) / "b.mp4"
            good.write_bytes(b"\0\0\0\x18ftypisom" + b"\0" * 8 + b"moov" + b"\0" * 32 + b"mdat")
            bad.write_bytes(b"\0\0\0\x18ftypisom" + b"\0" * 8 + b"mdat" + b"\0" * 32 + b"moov")
            self.assertTrue(SC.is_faststart(good))
            self.assertFalse(SC.is_faststart(bad))

    def test_real_catalog_examples_are_valid(self):
        cat = json.loads((ROOT / "skills" / "reel" / "styles" / "catalog.json").read_text())
        self.assertEqual(cat["version"], 2)
        ids = {s["id"] for s in cat["styles"]}
        for style, ex in SC.iter_examples(cat):
            self.assertTrue(style is None or style in ids)
            self.assertEqual(ex["kind"], "showcase")
            for key in ("title", "person", "reel", "src", "poster", "seconds"):
                self.assertIn(key, ex)
            if style is None:
                self.assertIn("style_label", ex)


class ArollFixTests(unittest.TestCase):
    def test_added_repeats_ignores_source_stills(self):
        cut = [2.0, 0.01, 2.0, 0.0, 1.5]
        src = [2.0, 2.0, 2.0, 0.0, 1.5]       # the source itself is still at index 3
        self.assertEqual(AF.added_repeats(cut, src), [1])

    def test_added_repeats_when_source_window_is_short(self):
        self.assertEqual(AF.added_repeats([0.0, 0.0], [3.0]), [0, 1])

    def test_summary_plain_words(self):
        m = {"total_added": 0, "frames": 100, "segments": [{"id": "a", "frames": 100, "added": 0, "at": []}]}
        self.assertIn("no repeated frames", AF.summary(m))
        m = {"total_added": 3, "frames": 100, "segments": [{"id": "a", "frames": 50, "added": 3, "at": [7, 9, 11]},
                                                         {"id": "b", "frames": 50, "added": 0, "at": []}]}
        self.assertIn("a 3/50 (frame 7)", AF.summary(m))

    def test_check_skips_without_aroll(self):
        with tempfile.TemporaryDirectory() as d:
            res = AF.check(d)
        self.assertTrue(res["pass"])
        self.assertTrue(res.get("skipped"))
        self.assertEqual(res["name"], "aroll_repeats")


if __name__ == "__main__":
    unittest.main()
