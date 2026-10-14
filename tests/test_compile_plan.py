"""compile_plan unit tests (no network, no render): python -m unittest tests/test_compile_plan.py (from the repo root)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "reel" / "engine"))

import compile_plan as CP  # noqa: E402
from compile import common as C  # noqa: E402
from compile import heroes as H  # noqa: E402
from compile import items as I  # noqa: E402
from compile import split_deck, motion_editorial  # noqa: E402
from compile import split_engine as SE  # noqa: E402
from compile import validate as V  # noqa: E402
from compile.kinds import classify  # noqa: E402

EDL = [{"id": "a", "clip": "c1", "in": 0.0, "out": 1.0, "mode": "full", "line": "Video editors are cooked.", "lock_in": True},
       {"id": "b", "clip": "c1", "in": 2.0, "out": 4.0, "mode": "full", "line": "It's 100% edited with Claude."},
       {"id": "c", "clip": "c1", "in": 5.0, "out": 7.0, "mode": "full", "line": "The graphics, the animations."},
       {"id": "d", "clip": "c1", "in": 8.0, "out": 9.0, "mode": "full", "line": "Comment the word EDIT and I'll share it."}]
SEGS = [{"id": "a", "frame": 0, "frames": 30}, {"id": "b", "frame": 30, "frames": 60},
        {"id": "c", "frame": 90, "frames": 60}, {"id": "d", "frame": 150, "frames": 30}]
WORDS = [{"text": t, "start": s, "end": s + 0.2} for t, s in [
    ("Video", 0.0), ("editors", 0.25), ("are", 0.5), ("cooked.", 0.7), ("It's", 1.0), ("100%", 1.3), ("edited", 1.6),
    ("with", 1.9), ("Claude.", 2.2), ("The", 3.0), ("graphics,", 3.3), ("the", 3.7), ("animations.", 4.0),
    ("Comment", 5.0), ("the", 5.2), ("word", 5.4), ("EDIT", 5.6), ("and", 5.8)]]


def beat(i, comp="none", text="", anchor="", style="split-deck", **kw):
    line = next(e["line"] for e in EDL if e["id"] == i)
    return {"id": i, "line": line, "section": "s", "style": style, "purpose": "proof", "component": comp,
            "on_screen_text": text, "anchor_word": anchor, "hero": False, **kw}


def plan():
    return {"title": "Video editors are cooked", "hook": {"pick": "a"},
            "sections": [{"name": "s", "style": "split-deck", "purpose": "proof", "line_ids": ["a", "b", "c", "d"]}],
            "hero_moments": [{"line_id": "a", "anchor_word": "cooked", "idea": "COOKED slams in on a hot set, char marks."}],
            "beats": [beat("a", "custom", None, "cooked", hero=True, visual_intent="COOKED slams in on a hot set, char marks."),
                      beat("b", "odometer", "100%", "100%"),
                      beat("c", "checklist-tick", "Graphics\nAnimations", "graphics"),
                      beat("d", "comment-cta", "EDIT", "EDIT")]}


def make_project(tmp, p=None):
    proj = Path(tmp)
    (proj / "work").mkdir()
    for name, data in (("edl.json", EDL), ("segments.json", SEGS), ("words.json", WORDS),
                       ("project.json", {"slug": "t", "joins_ok": [{"a": "a", "b": "b", "why": "listened"}],
                                         "motion": {"level": "showreel"}})):
        (proj / name).write_text(json.dumps(data))
    (proj / "work" / "plan_fast.json").write_text(json.dumps(p or plan()))
    ledger = {"entries": [{"src": "caption", "value": "100", "t0": 1.3, "t1": 1.5, "seg": "b", "status": "verified",
                           "reason": "fixture"}], "stats": {"verified": 1}}
    (proj / "work" / "numbers.json").write_text(json.dumps(ledger))     # numcheck.py ledger (compile number gate)
    return proj


class ValidateTests(unittest.TestCase):
    def test_good_plan_passes(self):
        V.check_plan(plan(), EDL)

    def test_errors_name_the_beat(self):
        p = plan()
        p["beats"][1] = beat("b", "odometer", "250%", "100%")
        p["beats"][2] = beat("c", "sparkles", "", "the")
        with self.assertRaises(C.CompileError) as cm:
            V.check_plan(p, EDL)
        self.assertIn("beat b:", str(cm.exception))
        self.assertIn("beat c: bad component", str(cm.exception))

    def test_em_dash_and_anchor(self):
        self.assertIn("em dash", V.check_plain(beat("b", "label-pill", "edited — Claude", "edited"),
                                               EDL[1]["line"], ""))
        self.assertIn("anchor_word", V.check_plain(beat("b", "label-pill", "Claude", "banana"), EDL[1]["line"], ""))

    def test_line_drift_and_coverage(self):
        p = plan()
        p["beats"][1] = {**p["beats"][1], "line": "something else"}
        p["beats"] = p["beats"][:3] + []
        with self.assertRaises(C.CompileError) as cm:
            V.check_plan(p, EDL)
        msg = str(cm.exception)
        self.assertIn("segment d: has no beat", msg)
        self.assertIn("beat b: line text differs", msg)

    def test_hero_needs_idea(self):
        self.assertIn("visual_intent", V.check_hero({"component": "custom", "visual_intent": "x", "anchor_word": "cooked"},
                                                   EDL[0]["line"]))


class HelperTests(unittest.TestCase):
    def test_title_lines_and_numbers(self):
        self.assertEqual(C.title_lines("Video editors are cooked"), ("Video editors", "are cooked"))
        self.assertEqual(C.number_in("100%"), ("100%", ""))
        self.assertEqual(C.number_in("7 days to go")[0], "7")
        self.assertEqual(C.number_in("no digits"), (None, "no digits"))

    def test_split_items_and_arrow(self):
        self.assertEqual(C.split_items("Claude, ChatGPT, right skill"), ["Claude", "ChatGPT", "right skill"])
        self.assertEqual(C.split_items("Graphics\nAnimations"), ["Graphics", "Animations"])
        self.assertEqual(C.arrow_split("boring yaps → edited videos"), ("boring yaps", "→", "edited videos"))

    def test_anchor_safe_tokens(self):
        seg = [{"text": "100%", "start": 0, "end": 1}, {"text": "covid-19", "start": 1, "end": 2}]
        self.assertEqual(C.anchor_for("100%", seg), "@100")
        self.assertEqual(C.anchor_for("covid-19", seg), "@covid")
        self.assertIsNone(C.anchor_for("banana", seg))

    def test_odometer_parse(self):
        a = I.odometer({"value": "100%", "anchor": "@100"})["args"]
        self.assertEqual((a["value"], a["suffix"], a["decimals"], a["land"]), (100.0, "%", 0, "@100"))
        self.assertEqual(I.odometer({"value": "1,000"})["args"]["value"], 1000.0)
        self.assertEqual(I.odometer({"value": "$7.5"})["args"]["prefix"], "$")

    def test_keyword_from_phrase(self):
        self.assertEqual(I.keyword_of("comment the word EDIT", "@edit"), "EDIT")
        self.assertEqual(I.keyword_of("EDIT", "@edit"), "EDIT")

    def test_comment_uses_spoken_words(self):
        a = I.comment({"text": "EDIT", "anchor": "@edit"}, EDL[3]["line"])["args"]
        self.assertEqual(a["dm_text"], "I'll share it")


class KindTests(unittest.TestCase):
    def seg(self, i):
        return C.seg_words(WORDS, C.windows(SEGS)[i])

    def test_kinds(self):
        self.assertEqual(classify(beat("a"), self.seg("a"))["kind"], "none")
        s = classify(beat("b", "odometer", "100%", "100%"), self.seg("b"))
        self.assertEqual((s["kind"], s["value"], s["anchor"]), ("stat", "100%", "@100"))
        s = classify(beat("c", "checklist-tick", "Graphics\nAnimations", "graphics"), self.seg("c"))
        self.assertEqual((s["kind"], s["ticks"]), ("list", ["@graphics", "@animations"]))
        s = classify(beat("c", "stepper", "graphics", "graphics"), self.seg("c"))
        self.assertEqual(s["kind"], "word")

    def test_empty_text_is_caption_only(self):
        s = classify(beat("c", "annotation-arrow", "", "graphics"), self.seg("c"))
        self.assertEqual((s["kind"], s["dropped"]), ("none", True))


class WriterTests(unittest.TestCase):
    def test_punch_runs_alternate(self):
        rows = [{"id": x, "mode": "full", "top": None} for x in "abcd"]
        self.assertEqual([r.get("punch") for r in SE.punch_runs(rows)], [None, SE.PUNCH, None, SE.PUNCH])
        rows[1] = {"id": "b", "mode": "split", "top": {"insert": "x"}}
        self.assertEqual([r.get("punch") for r in SE.punch_runs(rows)], [None, None, None, SE.PUNCH])

    def test_calm_talk_only_on_caption_shots(self):
        rows = SE.calm_talk([{"id": "a", "mode": "full", "top": None}, {"id": "b", "mode": "split", "top": {"insert": "x"}}])
        self.assertEqual(rows[0]["motion"], {"level": "simple"})
        self.assertNotIn("motion", rows[1])

    def test_caption_chunks_avoid_binding_breaks(self):
        sys.path.insert(0, str(ROOT / "skills" / "reel" / "templates" / "split"))
        import captions as CAPS
        ph = [{"text": w, "start": i * 0.2, "end": i * 0.2 + 0.15}
              for i, w in enumerate("And you can do it now because Claude can turn".split())]
        for chunk in CAPS.split_phrase(ph, 3, 26)[:-1]:
            self.assertNotIn(CAPS._bare(chunk[-1]["text"]), CAPS.BIND)

    def test_edl_keeps_takes(self):
        out = SE.edl_with([{**EDL[0], "top": "old", "punch": 1.2}], [{"id": "a", "mode": "split", "top": {"insert": "x"}}])
        self.assertEqual(out[0]["lock_in"], True)
        self.assertEqual(out[0]["in"], 0.0)
        self.assertNotIn("punch", out[0])
        self.assertEqual(out[0]["top"], {"insert": "x"})

    def test_first_segment_hook_and_beat(self):
        shot = {"kind": "word", "text": "cooked", "anchor": "@cooked", "hero": True}
        rows, beats = split_deck.rows_and_beats([("a", shot)], {"a": EDL[0]["line"]}, "Video editors are cooked")
        self.assertEqual((rows[0]["top"]["insert"], rows[0]["top"]["args"]["comp"]), ("hero", "title-stamp"))
        self.assertEqual(rows[0]["top"]["args"]["text"], "Video editors")
        self.assertEqual(beats[0]["at_word"], "cooked")

    def test_motion_editorial_word(self):
        mode, top = motion_editorial.top_for({"kind": "word", "text": "EDIT", "anchor": "@edit", "hero": False}, "")
        self.assertEqual((mode, top["insert"]), ("card", "kinetic"))
        self.assertEqual(top["args"]["lines"][0]["text"], "EDIT")


class StyleTests(unittest.TestCase):
    def test_multi_style_needs_override(self):
        p = plan()
        p["sections"] = [{**p["sections"][0], "line_ids": ["a"]},
                         {"name": "t", "style": "clean-talk", "purpose": "proof", "line_ids": ["b", "c", "d"]}]
        with self.assertRaises(C.CompileError) as cm:
            CP.pick_style(p, None)
        self.assertIn("Multi-style", str(cm.exception))
        self.assertEqual(CP.pick_style(p, "motion-editorial"), "motion-editorial")
        with self.assertRaises(C.CompileError):
            CP.pick_style(p, "floating-cards")


class HeroTests(unittest.TestCase):
    def test_offline_pick_is_spoken_word(self):
        b = plan()["beats"][0]
        self.assertEqual(H.offline_pick(b)["on_screen_text"], "cooked")

    def test_llm_choice_validated_and_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            good = {"data": {"component": "label-pill", "on_screen_text": "cooked", "anchor_word": "cooked"},
                    "attempts": [{"model": "m", "secs": 0, "cost": 0.001, "error": None}]}
            lib = {"hero": "none", "args": {}, "source": "llm"}
            with mock.patch.object(H.LR, "typed", return_value=good) as typed, \
                    mock.patch.object(H.HL, "ask", return_value=lib) as ask:
                r = H.resolve(proj, plan()["beats"], {}, "split-deck", split_deck.HERO_COMPONENTS)
                H.resolve(proj, plan()["beats"], {}, "split-deck", split_deck.HERO_COMPONENTS)
            self.assertEqual((typed.call_count, ask.call_count), (1, 1))
            self.assertEqual(r["fallbacks"]["a"]["source"], "llm")
            todo = json.loads((proj / H.TODO).read_text())
            self.assertEqual((todo[0]["line_id"], todo[0]["status"]), ("a", "todo"))

    def test_failed_llm_falls_back_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            bad = {"data": None, "attempts": [{"model": "m", "secs": 0, "cost": 0, "error": "boom"}]}
            with mock.patch.object(H.LR, "typed", return_value=bad):
                r = H.resolve(proj, plan()["beats"], {}, "split-deck", split_deck.HERO_COMPONENTS)
            self.assertEqual(r["fallbacks"]["a"]["source"], "offline")


class CompileTests(unittest.TestCase):
    def test_compile_writes_inputs_and_keeps_waivers(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            rep = CP.compile_project(proj, "work/plan_fast.json", None, use_llm=False)
            self.assertEqual(rep["style"], "split-deck")
            pj = json.loads((proj / "project.json").read_text())
            self.assertEqual(pj["joins_ok"][0]["why"], "listened")
            self.assertEqual(pj["motion"]["captions"], "plain")
            self.assertEqual(pj["motion"]["level"], "simple")
            self.assertEqual(pj["motion"]["sfx"], "light")
            edl = json.loads((proj / "edl.json").read_text())
            self.assertEqual([e["mode"] for e in edl], ["split", "split", "split", "split"])
            self.assertEqual(edl[2]["top"]["insert"], "beat")          # everyday beat (compile/everyday.py)
            self.assertEqual(edl[2]["top"]["args"]["comp"], "ed-checklist")
            self.assertTrue((proj / "work" / "edl.before-compile.json").exists())
            self.assertTrue((proj / "work" / "hero_todo.json").exists())

    def test_bad_plan_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = plan()
            p["beats"][1] = beat("b", "odometer", "edited — fast", "edited")
            proj = make_project(tmp, p)
            before = (proj / "edl.json").read_text()
            with self.assertRaises(C.CompileError):
                CP.compile_project(proj, "work/plan_fast.json", None, use_llm=False)
            self.assertEqual((proj / "edl.json").read_text(), before)


if __name__ == "__main__":
    unittest.main()
