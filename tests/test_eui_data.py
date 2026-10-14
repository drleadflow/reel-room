"""editorial-ui data heroes (compile/eui_data.py + editorial_ui.py) and the engine-wide CPU cap (engine/rrlimits.py).
No network, no render: python -m unittest tests/test_eui_data.py"""
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / "skills" / "reel"
sys.path.insert(0, str(SK / "engine"))
sys.path.append(str(SK / "templates" / "kit"))

import rrlimits as RL  # noqa: E402
from compile import editorial_ui as EU  # noqa: E402
from compile import eui_data as ED  # noqa: E402
from compile import hero_lib as HL  # noqa: E402

LINES = {"a": "Get in shape fast.", "b": "It could be eight weeks, 12 weeks, 16 weeks.", "c": "Studies show 33% less.",
         "d": "Number two, a deadline."}
WINS = {"a": (0.0, 2.0), "b": (2.0, 6.0), "c": (6.0, 9.0), "d": (9.0, 9.8)}
LOW_HEAD = {"cx": 540, "cy": 1100, "h": 260}      # room above the head
HIGH_HEAD = {"cx": 540, "cy": 600, "h": 300}      # no room above the head
COUNTER = {"steps": [["8", "@eight"], ["12", "@12"], ["16", "@16"]], "unit": "WEEKS", "kicker": "DEADLINE",
           "label": "short and compressed"}


def hero(hid, args, anchor="@weeks"):
    return {"kind": "hero", "hero_id": hid, "comp": hid, "args": dict(args), "hero": True, "anchor": anchor,
            "section": "s1", "purpose": "proof"}


def ctx(face, sources=""):
    return {"wins": WINS, "lines": LINES, "facepos": {k: face for k in WINS}, "sources": sources,
            "context": {k: "" for k in WINS}}


class DataHeroTests(unittest.TestCase):
    def test_editorial_ui_library_has_data_heroes(self):
        self.assertIn("money-counter", HL.allowed("editorial-ui", ""))
        self.assertIn("title-stamp", HL.allowed("editorial-ui", ""))
        self.assertNotIn("evidence-hero", HL.allowed("editorial-ui", ""))          # needs sources
        self.assertIn("evidence-hero", HL.allowed("editorial-ui", "Cai 2023"))

    def test_counter_fits_or_trims(self):
        self.assertEqual(ED.fit_counter(COUNTER, 900), COUNTER)
        small = ED.fit_counter(COUNTER, 250)
        self.assertEqual((small.get("bars"), "kicker" in small, "label" in small), (False, False, False))
        self.assertIsNone(ED.fit_counter(COUNTER, 120))
        self.assertGreater(ED.band_height(LOW_HEAD), 400)
        self.assertLess(ED.band_height(HIGH_HEAD), 200)

    def test_route_keeps_counter_on_its_own_set(self):
        shots, notes = ED.route([("b", hero("money-counter", COUNTER))], ctx(LOW_HEAD), HL.STYLE_ONLY["editorial-ui"])
        self.assertTrue(shots[0][1]["data_set"])
        beats, need, _ = EU.editorial_beats([("a", {"kind": "none"})] + shots, LINES, "Get in shape", WINS)
        b = beats["b"]
        self.assertEqual((b["scene"], b["zoom"], b["headlines"]), ("set", 1.0, []))
        self.assertEqual((b["cards"][0]["comp"], b["cards"][0]["data"], b["cards"][0]["matte"]),
                         ("money-counter", True, False))
        self.assertIn([60, 180], need)                                   # its set frames need the cut-out

    def test_no_room_substitutes_with_a_note(self):
        shots, notes = ED.route([("b", hero("money-counter", COUNTER))], ctx(HIGH_HEAD), HL.STYLE_ONLY["editorial-ui"])
        self.assertEqual((shots[0][1]["kind"], shots[0][1]["value"], shots[0][1]["label"]), ("stat", "16", "WEEKS"))
        self.assertIn("no room above the head", notes[0])
        short, notes = ED.route([("d", hero("money-counter", COUNTER))], ctx(LOW_HEAD), HL.STYLE_ONLY["editorial-ui"])
        self.assertIn("its cut is 0.8 s", notes[0])

    def test_title_stamp_becomes_a_set_headline(self):
        shots, notes = ED.route([("a", {"kind": "none"}), ("d", hero("title-stamp", {"text": "DEADLINE",
                                                                                     "land": "@deadline"}))],
                                ctx(LOW_HEAD), HL.STYLE_ONLY["editorial-ui"])
        self.assertEqual((shots[1][1]["kind"], shots[1][1]["stamp"]), ("word", True))
        self.assertIn("colour-set headline", notes[0])

    def test_evidence_citation_must_be_in_sources(self):
        ev = {"kind": "bar", "citation": "Cai 2023, Prev Med", "series": [{"name": "risk", "values": [33]}],
              "labels": ["no", "yes"], "stat": "33%"}
        shots, notes = ED.route([("c", hero("evidence-hero", ev, "@33%"))], ctx(LOW_HEAD, ""),
                                HL.STYLE_ONLY["editorial-ui"])
        self.assertEqual(shots[0][1]["kind"], "stat")
        self.assertIn("sources.txt", notes[0])

    def test_unknown_hero_and_cap_are_logged(self):
        notes = []
        many = [(str(i), hero("word-stamp", {})) for i in range(7)]
        EU.cap_heroes(many, notes)
        self.assertEqual(len(notes), 2)
        shots, notes = ED.route([("b", hero("nle-timeline", {}))], ctx(LOW_HEAD), HL.STYLE_ONLY["editorial-ui"])
        self.assertEqual(shots[0][1]["kind"], "word")
        self.assertIn("not drawn by editorial-ui", notes[0])
        pn = ED.planner_notes([{"id": "b", "library": "cycle-chart"}], {"b": {"hero": "none"}},
                              HL.STYLE_ONLY["editorial-ui"])
        self.assertIn("planner asked for cycle-chart", pn[0])

    def test_source_card(self):
        card = EU.card_for({"kind": "source", "text": "Cai 2023", "anchor": "@studies"}, "Studies show", "", "dark")
        self.assertEqual((card["kind"], card["label"], card["text"]), ("status", "SOURCE", "Cai 2023"))


class CaptionAndCounterTests(unittest.TestCase):
    def test_chunk_never_ends_on_a_number(self):
        """editorial-ui subtitles use split/captions.py: 'here are the 3 | things' must not happen."""
        import importlib.util
        sys.path.insert(0, str(SK / "templates" / "split"))
        spec = importlib.util.spec_from_file_location("split_captions_for_test", SK / "templates" / "split" / "captions.py")
        cap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cap)
        ph = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25}
              for i, t in enumerate("here are the 3 things I would do.".split())]
        for mw, mc in ((4, 24), (3, 26)):
            got = [" ".join(w["text"] for w in c) for c in cap.split_phrase(ph, mw, mc)]
            self.assertFalse(any(g.split()[-1] == "3" for g in got[:-1]), got)
        self.assertTrue(cap._is_number("$60") and cap._is_number("0.24") and cap._is_number("30%"))
        self.assertFalse(cap._is_number("things"))

    def test_counter_clip_box_holds_its_line(self):
        """money-counter: the clipping box is padded (and the margin takes it back) so the number's line box stays
        inside it in every layout (textcheck 'clip'), split and editorial-ui alike."""
        import heroes_data as HD
        css = HD.MN_CSS
        self.assertIn("padding:.14em 0;", css)
        self.assertIn("margin:-.14em 0;", css)
        self.assertIn("clip-path:inset(9.5% -6% 9.5% -6%)", css)


class CpuCapTests(unittest.TestCase):
    def test_parse_and_budget(self):
        self.assertIsNone(RL.parse("off"))
        self.assertEqual(RL.parse("3"), 3)
        self.assertEqual(RL.parse(None), RL.default_threads())
        with mock.patch.dict(os.environ, {"RR_MAX_THREADS": "4"}):
            self.assertEqual((RL.max_threads(), RL.render_workers(6), RL.pool_workers(3, per_worker=2)), (4, 4, 2))
        with mock.patch.dict(os.environ, {"RR_MAX_THREADS": "off"}):
            self.assertEqual((RL.render_workers(6), RL.wrap(["ffmpeg", "-i", "a", "b"])), (6, ["ffmpeg", "-i", "a", "b"]))

    def test_ffmpeg_args(self):
        got = RL.ffmpeg_args(["-y", "-ss", "1", "-i", "a.mp4", "-i", "b.wav", "-c:v", "libx264", "o.mp4"], 3)
        self.assertEqual(got[:2], ["-filter_threads", "3"])
        self.assertEqual(got.count("-threads"), 3)                     # 2 inputs + the output
        self.assertEqual(got[-3:], ["-threads", "3", "o.mp4"])          # output option, before the output file
        own = RL.ffmpeg_args(["-y", "-i", "a.mp4", "-c:v", "libx264", "-threads", "12", "o.mp4"], 3)
        self.assertEqual(own.count("-threads"), 1)                     # the caller's own: never a second one
        self.assertEqual(own[own.index("-threads") + 1], "3")           # only lowered
        keep = RL.ffmpeg_args(["-threads", "1", "-i", "a.mp4", "-f", "null", "-"], 3)
        self.assertEqual((keep.count("-threads"), keep[keep.index("-threads") + 1]), (1, "1"))   # smaller value kept
        fc = RL.ffmpeg_args(["-i", "a", "-filter_complex", "[0]null", "o.mp4"], 2)
        self.assertIn("-filter_complex_threads", fc)
        self.assertEqual(RL.ffmpeg_args(["-version"], 2), ["-version"])

    def test_ffprobe_and_share(self):
        self.assertEqual(RL.ffprobe_args(["-v", "error", "x.mp4"], 2), ["-v", "error", "x.mp4"])   # probing: untouched
        argv = ["x.mp4", "-threads", "4", "-show_streams"]
        self.assertEqual(RL.ffprobe_args(argv, 7), argv)
        with mock.patch.dict(os.environ, {"RR_MAX_THREADS": "8"}):
            self.assertEqual(RL.share(3), 2)
            self.assertEqual(RL.ffmpeg_threads(), 2)
            os.environ.pop("RR_FFMPEG_THREADS", None)

    def test_real_ffprobe_and_ffmpeg_through_the_shim(self):
        """HyperFrames-style calls (input first, own -threads) through the PATH shim with a real binary."""
        import shutil
        import subprocess
        import tempfile
        if os.name == "nt" or not shutil.which("ffmpeg", path=os.environ["PATH"].replace(str(RL.SHIM_DIR), "")):
            self.skipTest("no ffmpeg")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"RR_MAX_THREADS": "7"}):
            env = {**os.environ, **RL.env_for(7)}
            clip = os.path.join(tmp, "c.mp4")
            subprocess.run([str(RL.SHIM_DIR / "ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc=size=64x64:rate=30:duration=0.5", "-c:v", "libx264", "-threads", "12", clip],
                           check=True, env=env, capture_output=True)
            for argv in (["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
                         [clip, "-v", "error", "-threads", "4", "-show_streams"],
                         ["-v", "error", "-threads", "2", "-i", clip, "-show_format"]):
                p = subprocess.run([str(RL.SHIM_DIR / "ffprobe")] + argv, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)

    def test_no_absolute_ffmpeg_paths(self):
        """Every engine / template ffmpeg call resolves through PATH or ffmpeg_bin() (both reach the cap)."""
        bad = []
        for root in (SK / "engine", SK / "templates"):
            for f in root.rglob("*.py"):
                txt = f.read_text(errors="ignore")
                if re.search(r"[\"'](/[^\"']+/)ff(mpeg|probe)[\"']", txt) or \
                        re.search(r"which\(\s*[\"']ff(mpeg|probe)", txt) and f.name != "rrlimits.py":
                    bad.append(str(f.relative_to(SK)))
        self.assertEqual([b for b in bad if not b.endswith(("common.py", "doctor.py"))], [])


if __name__ == "__main__":
    unittest.main()
