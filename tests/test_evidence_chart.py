"""evidence-chart kit piece (templates/kit/comps_chart.py): python -m unittest tests/test_evidence_chart.py (repo root)."""
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent / "skills" / "reel" / "templates" / "kit"
sys.path.insert(0, str(KIT))

import rrkit  # noqa: E402

WORDS = [{"text": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in
         enumerate("nicotine clamps down on blood vessels and cuts blood flow much longer".split())]
LINE = dict(kind="line", citation="Chaumont et al., Sci Rep 2018", labels=["BSL", "1", "2"],
            series=[{"name": "sham", "values": [0, 140, 315]}, {"name": "nicotine", "values": [0, 90, 243]}])


class EvidenceChart(unittest.TestCase):
    def kit(self):
        return rrkit.Kit(None, WORDS)

    def test_registered(self):
        self.assertIn("evidence-chart", rrkit.COMPONENTS)
        self.assertTrue(callable(getattr(rrkit.Kit, "evidence_chart")))
        self.assertTrue(rrkit.COMPONENTS["evidence-chart"]["say"])

    def test_citation_is_required_and_shown(self):
        with self.assertRaises(ValueError):
            self.kit().evidence_chart(**{**LINE, "citation": "  "})
        p = self.kit().evidence_chart(**LINE)
        self.assertIn("Chaumont et al., Sci Rep 2018", p.html)
        self.assertIn('data-box="card"', p.html)

    def test_values_must_match_labels(self):
        bad = {**LINE, "series": [{"name": "x", "values": [1, 2]}]}
        with self.assertRaises(ValueError):
            self.kit().evidence_chart(**bad)
        with self.assertRaises(ValueError):
            self.kit().evidence_chart(**{**LINE, "kind": "pie"})

    def test_times_follow_words_in_any_order(self):
        p = self.kit().evidence_chart(**LINE, stat="33%", stat_label="less dilation", draw="@flow", stamp="@clamps")
        t = p.meta["times"]
        self.assertLess(t["stamp"], t["draw"])            # stamp word comes before the draw word: both resolve
        self.assertGreater(t["out"], t["draw"])
        kinds = [e["kind"] for e in p.events("light")]
        self.assertEqual(kinds, ["pop", "stamp"])
        self.assertIn("whoosh", [e["kind"] for e in p.events("full")])

    def test_bar_highlight_ring_and_dim(self):
        p = self.kit().evidence_chart(kind="bar", citation="Lei et al., Sci Rep 2017", labels=["0 h", "72 h"],
                                      series=[{"name": "control", "values": [100, 8]}, {"name": "nicotine", "values": [100, 56]}],
                                      highlight=[1, 1], highlight_at="@longer")
        self.assertIn("ec-ring", p.html)
        self.assertTrue(any(".ec-bar:not(.ec-b1-1)" in j for j in p.js))
        self.assertIsNotNone(p.meta["times"]["highlight"])

    def test_js_is_seek_safe(self):
        p = self.kit().evidence_chart(**LINE)
        self.assertTrue(all("immediateRender:false" in j for j in p.js if "fromTo" in j))
        self.assertFalse(any("Math.random" in j for j in p.js))


if __name__ == "__main__":
    unittest.main()
