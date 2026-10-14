"""Phrasebook checks: styles/phrasebook.json is valid, plain, and matches the copy built into the Room page.
python -m unittest tests/test_phrasebook.py (from the repo root)."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "reel"
JSON_PATH = SKILL / "styles" / "phrasebook.json"
PAGE = SKILL / "room" / "reel-room.html"
DOC = SKILL / "references" / "phrasebook.md"
ITEM_KEYS = ("id", "group", "say", "does", "action", "needs_word")
EM_DASH = chr(0x2014)
ACTION_TYPES = {"level", "edit", "motion", "project", "behind", "kit", "insert", "grade", "pacing"}


def built_in():
    m = re.search(r"const PHRASEBOOK = (\{.*?\});\n", PAGE.read_text(encoding="utf-8"))
    assert m, "PHRASEBOOK constant not found in reel-room.html"
    return json.loads(m.group(1))


class Phrasebook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pb = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    def test_shape(self):
        groups = {g["id"] for g in self.pb["groups"]}
        ids = [p["id"] for p in self.pb["items"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate phrase ids")
        for p in self.pb["items"]:
            self.assertIn(p["group"], groups, p["id"])
            self.assertTrue(p["say"].strip() and p["does"].strip(), p["id"])
            self.assertIn(p["action"]["type"], ACTION_TYPES, p["id"])
            self.assertEqual("{word}" in p["say"], bool(p.get("needs_word")), p["id"])

    def test_plain_language(self):
        text = JSON_PATH.read_text(encoding="utf-8")
        self.assertNotIn(EM_DASH, text, "no em dashes")
        self.assertNotIn(EM_DASH, DOC.read_text(encoding="utf-8"), "no em dashes in phrasebook.md")

    def test_every_phrase_documented(self):
        doc = DOC.read_text(encoding="utf-8")
        missing = [p["id"] for p in self.pb["items"] if f"`{p['id']}`" not in doc]
        self.assertEqual(missing, [], "phrase ids missing from references/phrasebook.md")

    def test_page_copy_matches_file(self):
        page = built_in()
        self.assertEqual(page["groups"], self.pb["groups"])
        self.assertEqual(page.get("examples"), self.pb.get("examples"))
        trim = lambda p: {k: p[k] for k in ITEM_KEYS if p.get(k) is not None and p.get(k) is not False}
        self.assertEqual([trim(p) for p in page["items"]], [trim(p) for p in self.pb["items"]])

    def test_page_loads_the_file(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertIn('fetch("phrasebook.json"', html)
        self.assertIn("loadPhrasebook();", html)

    def test_quick_asks_exist(self):
        html = PAGE.read_text(encoding="utf-8")
        quick = json.loads(re.search(r"const QUICK = (\[.*?\]);", html).group(1))
        ids = {p["id"] for p in self.pb["items"]}
        self.assertEqual([q for q in quick if q not in ids], [])


if __name__ == "__main__":
    unittest.main()
