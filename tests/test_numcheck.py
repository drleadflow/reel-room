"""On-screen number verification (engine/numwords.py, numcheck.py, numgate.py, compile_plan.number_gate). No network,
no Whisper: the second reading and the model verdict are injected. python -m unittest tests/test_numcheck.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "reel" / "engine"))

import compile_plan as CP  # noqa: E402
import numcheck as NC  # noqa: E402
import numgate as NG  # noqa: E402
import numwords as NW  # noqa: E402
from compile.common import CompileError  # noqa: E402

EDL = [{"id": "a", "clip": "c1", "in": 0, "out": 3, "line": "If insulin is over 7, that means insulin resistance."},
       {"id": "b", "clip": "c1", "in": 3, "out": 6, "line": "Vapes went from $15 billion to $60 billion."},
       {"id": "c", "clip": "c1", "in": 6, "out": 9, "line": "It is 0.24 grams for younger men."}]
SEGS = [{"id": "a", "frame": 0, "frames": 90}, {"id": "b", "frame": 90, "frames": 90},
        {"id": "c", "frame": 180, "frames": 90}]
WORDS = [{"text": t, "start": s, "end": s + 0.25} for t, s in [
    ("If", 0.1), ("insulin", 0.4), ("is", 0.8), ("over", 1.0), ("7,", 1.3), ("that", 1.7), ("means", 2.0),
    ("Vapes", 3.1), ("went", 3.4), ("from", 3.6), ("$15", 3.9), ("billion", 4.2), ("to", 4.5), ("$60", 4.8),
    ("billion.", 5.1), ("It", 6.1), ("is", 6.3), ("0.24", 6.6), ("grams", 7.0)]]
# reading B (a fresh pass): hears 'seven' and '15' right, mishears 60 as 16 and 0.24 as 0.4
HEARD = [("If", 0.1), ("insulin", 0.4), ("is", 0.8), ("over", 1.0), ("seven,", 1.3), ("that", 1.7),
         ("Vapes", 3.1), ("went", 3.4), ("from", 3.6), ("$15", 3.9), ("billion", 4.2), ("to", 4.5), ("$16", 4.8),
         ("billion.", 5.1), ("It", 6.1), ("is", 6.3), ("0.4", 6.6), ("grams", 7.0)]


def fake_transcribe(a, b):
    return [{"w": w, "s": s, "e": s + 0.25, "p": 0.9} for w, s in HEARD if a <= s <= b]


def fake_judge(c, rb, ctx):
    agree = c["value"] in rb["values"]
    return {"agree": agree, "value": c["value"] if agree else (rb["values"] or ["0"])[0], "confidence": 0.95,
            "cost": 0}


def make_project(tmp, pj=None):
    proj = Path(tmp)
    (proj / "work").mkdir()
    for name, data in (("edl.json", EDL), ("segments.json", SEGS), ("words.json", WORDS),
                       ("project.json", pj or {"slug": "t"})):
        (proj / name).write_text(json.dumps(data))
    return proj


def run_check(proj):
    ledger = NC.verify(proj, transcribe=fake_transcribe, judge=fake_judge, dur=9.0, akey="x")
    ledger["removed_from_captions"] = NC.block_captions(proj, ledger)
    (proj / NC.LEDGER).write_text(json.dumps(ledger))
    return ledger


class NumWordsTests(unittest.TestCase):
    def test_digits_and_canon(self):
        self.assertEqual(NW.digits_in("$60 billion, 0.24 and 1,000 or 7,"), ["60", "0.24", "1000", "7"])
        self.assertEqual((NW.canon("07"), NW.canon("0.240"), NW.canon("x")), ("7", "0.24", None))

    def test_spoken_values(self):
        self.assertEqual(NW.spoken_values("if insulin is over seven, that"), {"7"})
        self.assertEqual(NW.spoken_values("zero point two four for men"), {"0.24"})
        self.assertIn("60", NW.spoken_values("sixty billion dollars"))
        self.assertNotIn("60", NW.spoken_values("16 billion dollars"))
        self.assertEqual(NW.spoken_values("eight weeks, twelve weeks, 16 weeks"), {"8", "12", "16"})

    def test_strip_numbers_words_only(self):
        self.assertEqual(NW.strip_numbers("30% more likely"), "more likely")
        self.assertEqual(NW.strip_numbers("8 WEEKS"), "WEEKS")


class VerdictTests(unittest.TestCase):
    def test_validator(self):
        chk = NC.check_verdict({"value": "7"})
        self.assertIsNone(chk({"agree": True, "value": "7", "confidence": 0.9}))
        self.assertIn("agree is true", chk({"agree": True, "value": "8", "confidence": 0.9}))
        self.assertIn("confidence", chk({"agree": False, "value": "8", "confidence": 3}))
        self.assertIn("agree must be", chk({"agree": "yes", "value": "7", "confidence": 0.9}))

    def test_decide(self):
        c, rb = {"value": "7"}, {"values": ["7"], "near": "over seven"}
        self.assertEqual(NC.decide(c, rb, {"agree": True, "value": "7", "confidence": 0.9})[0], "verified")
        self.assertIn("low confidence", NC.decide(c, rb, {"agree": True, "value": "7", "confidence": 0.5})[1])
        self.assertIn("disagree", NC.decide(c, {"values": ["16"], "near": "16"}, {"agree": True, "value": "7",
                                                                                   "confidence": 1})[1])
        self.assertIn("no model verdict", NC.decide(c, rb, {"error": "no key"})[1])


class LedgerTests(unittest.TestCase):
    def test_verify_blocks_misheard_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            ledger = run_check(proj)
            status = {e["value"]: e["status"] for e in ledger["entries"]}
            self.assertEqual(status, {"7": "verified", "15": "verified", "60": "blocked", "0.24": "blocked"})
            words = [w["text"] for w in json.loads((proj / "words.json").read_text())]
            self.assertNotIn("$60", words)
            self.assertNotIn("0.24", words)
            self.assertIn("7,", words)
            flags = NC.flags_doc(ledger)["flags"]
            self.assertEqual(sorted(f["value"] for f in flags), ["0.24", "60"])
            self.assertTrue((proj / "work" / "words.prenum.json").exists())

    def test_human_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, {"slug": "t", "numbers_ok": [{"value": "0.24", "t": 6.6, "why": "her card"}]})
            ledger = run_check(proj)
            self.assertEqual({e["value"]: e["status"] for e in ledger["entries"]}["0.24"], "confirmed")

    def test_speech_only_without_a_model(self):
        """No key / --no-llm: agreeing transcripts verify (tagged speech_only), disagreements stay blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            ledger = NC.verify(proj, transcribe=fake_transcribe, dur=9.0, akey="x", use_llm=False)
            by = {e["value"]: e for e in ledger["entries"]}
            self.assertEqual((by["7"]["status"], by["7"]["check"]), ("verified", "speech_only"))
            self.assertEqual((by["60"]["status"], by["0.24"]["status"]), ("blocked", "blocked"))
            self.assertIn("speech only", by["60"]["reason"])
            self.assertEqual((ledger["stats"]["mode"], ledger["stats"]["speech_only"]), ("speech_only", 2))

    def test_speech_only_needs_the_value_on_the_word(self):
        c = {"value": "8"}
        self.assertEqual(NC.decide(c, {"values": ["8", "12"], "at": ["12"], "near": "8 weeks 12"},
                                   NC.speech_judge(c, {}, ""))[0], "blocked")
        self.assertEqual(NC.decide(c, {"values": ["8"], "at": ["8"], "near": "8 weeks"},
                                   NC.speech_judge(c, {}, ""))[0], "verified")

    def test_no_key_falls_back_to_speech_only(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(NC, "has_key", return_value=False), \
                mock.patch.object(NC, "verify", return_value={"entries": [], "stats": {}}) as v:
            proj = make_project(tmp)
            NC.run(proj)
            self.assertEqual(v.call_args.kwargs["use_llm"], False)

    def test_groups_share_windows(self):
        cands = [{"t0": 1.0, "t1": 1.2}, {"t0": 2.0, "t1": 2.2}, {"t0": 20.0, "t1": 20.2}]
        self.assertEqual([len(g[2]) for g in NC.groups(cands, 30.0)], [2, 1])


EDITORIAL = {"beats": {
    "a": {"scene": "set", "set": "dark", "headlines": [{"at": 0, "text": "OVER 7|_insulin resistance_"}]},
    "b": {"scene": "room", "cards": [{"kind": "hero", "comp": "money-counter", "data": True, "matte": False,
                                      "args": {"steps": [["15", "@15"], ["60", "@60"]], "unit": "B", "at": "@from",
                                               "kicker": "VAPES"}}]},
    "c": {"scene": "set", "set": "tan", "headlines": [{"at": 0, "text": "0.24|_grams_"}]}}}


class GateTests(unittest.TestCase):
    def test_scrub_words_only_and_drop(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, {"slug": "t", "editorial": json.loads(json.dumps(EDITORIAL))})
            run_check(proj)
            self.assertEqual(len([b for b in NG.unverified(proj) if not b["where"].startswith("captions")]), 2)
            notes = NG.scrub(proj)
            beats = json.loads((proj / "project.json").read_text())["editorial"]["beats"]
            self.assertEqual(beats["a"]["headlines"][0]["text"], "OVER 7|_insulin resistance_")   # verified
            self.assertEqual(beats["b"]["cards"][0]["args"]["steps"], [["15", "@15"]])          # 60 dropped
            self.assertEqual(beats["c"]["headlines"][0]["text"], "_grams_")                     # words-only
            self.assertEqual(NG.unverified(proj), [])
            self.assertTrue(all("not verified" in n for n in notes))
            self.assertTrue(NG.check(proj)["pass"])

    def test_qa_gate_fails_without_ledger_and_on_new_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            self.assertFalse(NG.check(proj)["pass"])
            run_check(proj)
            self.assertTrue(NG.check(proj)["pass"])
            words = json.loads((proj / "words.json").read_text()) + [{"text": "16", "start": 8.0, "end": 8.2}]
            (proj / "words.json").write_text(json.dumps(words))
            res = NG.check(proj)
            self.assertFalse(res["pass"])
            self.assertIn("captions@8.00", res["detail"])

    def test_evidence_numbers_from_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, {"slug": "t", "editorial": {"beats": {"b": {"scene": "set", "cards": [
                {"kind": "hero", "comp": "evidence-hero", "data": True,
                 "args": {"citation": "Cai 2023, Prev Med", "series": [{"name": "risk", "values": [1, 1.3]}],
                          "labels": ["no", "yes"]}}]}}}})
            run_check(proj)
            self.assertTrue(NG.unverified(proj))
            (proj / "work" / "sources.txt").write_text("Cai 2023, Prev Med: odds 1 vs 1.3")
            self.assertEqual([b for b in NG.unverified(proj) if not b["where"].startswith("captions")], [])

    def test_compile_gate_needs_a_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp, {"slug": "t", "editorial": json.loads(json.dumps(EDITORIAL))})
            with self.assertRaises(CompileError):
                CP.number_gate(proj)
            run_check(proj)
            gate = CP.number_gate(proj)
            self.assertEqual(gate["numbers_gate"]["ledger"], True)
            self.assertTrue(gate["number_notes"])
            pj = json.loads((proj / "project.json").read_text())
            self.assertTrue(any("not verified" in n for n in pj["compiled"]["notes"]))


if __name__ == "__main__":
    unittest.main()
