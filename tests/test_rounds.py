"""rounds.py unit tests (no render, no ffmpeg): python -m unittest tests/test_rounds.py (from the repo root)."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import common as C  # noqa: E402
import hash as H  # noqa: E402
import rounds as RD  # noqa: E402
import snips as SN  # noqa: E402

EDL = [
    {"id": "s1", "clip": "c1", "in": 0.0, "out": 2.0, "mode": "full", "zoom": 1.0, "line": "so here is the thing"},
    {"id": "s2", "clip": "c1", "in": 3.0, "out": 5.0, "mode": "split", "zoom": 1.1, "top": "assets/card_a.png",
     "line": "insulin over seven matters"},
    {"id": "s3", "clip": "c1", "in": 6.0, "out": 8.0, "mode": "full", "zoom": 1.0, "line": "comment the word guide"},
]
STORY = {"beats": [{"t": 0.0, "line": "so here is the thing"}, {"t": 2.0, "line": "insulin over seven matters"},
                   {"t": 4.0, "line": "comment the word guide"}]}


def edl(proj):
    return C.read_json(Path(proj) / "edl.json")


def seg(proj, sid):
    return next(s for s in edl(proj) if s["id"] == sid)


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp(prefix="rr-rounds-"))
        (self.p / "assets").mkdir()
        (self.p / "assets" / "card_a.png").write_bytes(b"version-one")
        C.write_json(self.p / "edl.json", EDL)
        C.write_json(self.p / "project.json", {"slug": "t", "motion": {"level": "polished"},
                                               "beats": [{"at": 2.4, "insert": "number", "value": "7"}]})
        C.write_json(self.p / "work" / "storyboard.json", STORY)
        self.out = C.Out(False)

    def tearDown(self):
        shutil.rmtree(self.p, ignore_errors=True)

    def quiet(self, fn, *a, **k):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return fn(*a, **k)

    def snap(self, n):
        self.quiet(RD.cmd_snapshot, self.p, n, self.out)

    def set_top(self, sid, top):
        e = edl(self.p)
        for s in e:
            if s["id"] == sid:
                s["top"] = top
        C.write_json(self.p / "edl.json", e)


class Snapshot(Base):
    def test_snapshot_archives_beats_and_files(self):
        self.snap(None)
        d = self.p / "rounds" / "r1"
        for name in ("edl.json", "project.json", "beats.json", "meta.json", "storyboard.json"):
            self.assertTrue((d / name).exists(), name)
        beats = C.read_json(d / "beats.json")["beats"]
        self.assertEqual([b["id"] for b in beats], ["s1", "s2", "s3"])
        s2 = beats[1]
        self.assertIn("assets/card_a.png", s2["files"])
        self.assertTrue((self.p / "rounds" / "blobs" / s2["files"]["assets/card_a.png"]).exists())
        self.assertEqual(s2["rows"]["beats"][0]["value"], "7")      # row at 2.4 s sits in s2 (2.0 to 4.0)
        self.assertNotIn("clip", s2["look"])
        self.assertEqual(s2["timing"]["in"], 3.0)

    def test_next_round_number(self):
        self.snap(None)
        self.snap(None)
        self.assertEqual(RD.round_numbers(self.p), [1, 2])

    def test_index_lists_alts_only_for_changed_beats(self):
        self.snap(1)
        self.set_top("s2", "assets/card_b.png")
        self.snap(2)
        idx = RD.build_index(self.p)
        self.assertEqual([r["round"] for r in idx["rounds"]], [1, 2])
        self.assertEqual(idx["reel_level"], "polished")
        self.assertEqual(idx["segs"]["s2"]["alts"], [{"round": 1, "level": "polished"}])
        self.assertEqual(idx["segs"]["s1"]["alts"], [])
        self.assertEqual(RD.diff_rounds(self.p, 1, 2), [{"seg": "s2", "change": "look"}])

    def test_missing_round_is_plain_error(self):
        with self.assertRaises(ValueError) as e:
            RD.round_beats(self.p, 4)
        self.assertIn("no saved round 4", str(e.exception))


class UseRound(Base):
    def test_use_round_restores_look_not_timing(self):
        self.snap(1)
        self.set_top("s2", "assets/card_b.png")
        e = edl(self.p)
        e[1]["out"] = 5.5
        C.write_json(self.p / "edl.json", e)
        res = RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "use_round", "seg": "s2", "from_round": 1}]})
        self.assertTrue(res["results"][0]["ok"], res)
        self.assertEqual(res["changed"], ["s2"])
        self.assertEqual(res["rebuild"], "render")
        s2 = seg(self.p, "s2")
        self.assertEqual(s2["top"], "assets/card_a.png")
        self.assertEqual(s2["out"], 5.5)
        self.assertTrue((self.p / "work" / "beat_looks.json").exists())

    def test_use_round_with_timing_needs_assemble(self):
        self.snap(1)
        e = edl(self.p)
        e[1]["out"] = 5.5
        C.write_json(self.p / "edl.json", e)
        res = RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "use_round", "seg": "s2", "from_round": 1,
                                                      "timing": True}]})
        self.assertEqual(res["rebuild"], "assemble")
        self.assertEqual(seg(self.p, "s2")["out"], 5.0)

    def test_changed_file_comes_back_beside_current(self):
        self.snap(1)
        (self.p / "assets" / "card_a.png").write_bytes(b"version-two")
        RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "use_round", "seg": "s2", "from_round": 1}]})
        self.assertEqual(seg(self.p, "s2")["top"], "assets/rounds/r1/card_a.png")
        self.assertEqual((self.p / "assets" / "rounds" / "r1" / "card_a.png").read_bytes(), b"version-one")
        self.assertEqual((self.p / "assets" / "card_a.png").read_bytes(), b"version-two")   # never overwritten

    def test_split_piece_finds_base_segment(self):
        self.snap(1)
        e = edl(self.p)
        e[1]["id"] = "s2~1"
        e[1]["top"] = "assets/card_b.png"
        C.write_json(self.p / "edl.json", e)
        res = RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "use_round", "seg": "s2~1", "from_round": 1}]})
        self.assertTrue(res["results"][0]["ok"], res)
        self.assertEqual(seg(self.p, "s2~1")["top"], "assets/card_a.png")

    def test_unknown_round_and_kind_fail_per_change(self):
        res = RD.apply_doc(self.p, {"beat_changes": [
            {"id": "a", "kind": "use_round", "seg": "s2", "from_round": 9},
            {"id": "b", "kind": "teleport", "seg": "s2"},
            {"id": "c", "kind": "simpler", "seg": "s2", "status": "applied"}]})
        self.assertEqual([(r["id"], r["ok"]) for r in res["results"]], [("a", False), ("b", False)])
        self.assertEqual(res["rebuild"], "nothing")


class Levels(Base):
    def test_level_showreel_then_back_to_reel(self):
        res = RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "level", "seg": "s1", "level": "showreel"}]})
        self.assertEqual(res["rebuild"], "render")
        m = seg(self.p, "s1")["motion"]
        self.assertEqual(m["level"], "showreel")
        self.assertIn(m["transition"], RD.SHOW_MOVES)
        self.assertEqual(m["from_level"], ["camera", "transition"])
        RD.apply_doc(self.p, {"beat_changes": [{"id": "y", "kind": "level", "seg": "s1", "level": "reel"}]})
        self.assertNotIn("motion", seg(self.p, "s1"))

    def test_level_keeps_user_overrides(self):
        e = edl(self.p)
        e[0]["motion"] = {"transition": "whip"}
        C.write_json(self.p / "edl.json", e)
        RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "level", "seg": "s1", "level": "simple"}]})
        m = seg(self.p, "s1")["motion"]
        self.assertEqual((m["transition"], m["camera"], m["level"]), ("whip", "still", "simple"))

    def test_simpler_steps_down_and_stops_at_simple(self):
        RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "level", "seg": "s3", "level": "showreel"}]})
        r = RD.apply_doc(self.p, {"beat_changes": [{"id": "y", "kind": "simpler", "seg": "s3"}]})
        self.assertIn("Showreel to Polished", r["results"][0]["message"])
        RD.apply_doc(self.p, {"beat_changes": [{"id": "z", "kind": "simpler", "seg": "s3"}]})
        self.assertEqual(RD.seg_level(seg(self.p, "s3"), {}), "simple")
        r = RD.apply_doc(self.p, {"beat_changes": [{"id": "w", "kind": "simpler", "seg": "s3"}]})
        self.assertTrue(r["results"][0]["ok"])
        self.assertIn("already Simple", r["results"][0]["message"])
        self.assertEqual(r["changed"], [])

    def test_reel_level_writes_project(self):
        res = RD.apply_doc(self.p, {"motion_choice": {"level": "showreel"}})
        self.assertTrue(res["reel_changed"])
        self.assertEqual(res["rebuild"], "render")
        self.assertEqual(C.read_json(self.p / "project.json")["motion"]["level"], "showreel")
        again = RD.apply_doc(self.p, {"motion_choice": {"level": "showreel"}})
        self.assertEqual(again["rebuild"], "nothing")

    def test_motion_beats_need_current_storyboard_hash(self):
        stale = RD.apply_doc(self.p, {"motion_beats": {"levels": {"1": "showreel"}, "for": "oldhash"}})
        self.assertEqual(stale["changed"], [])
        self.assertTrue(any("older storyboard" in n for n in stale["notes"]))
        h = H.hash_beats(STORY["beats"])
        ok = RD.apply_doc(self.p, {"motion_beats": {"levels": {"1": "showreel"}, "for": h}})
        self.assertEqual(ok["changed"], ["s2"])
        self.assertEqual(seg(self.p, "s2")["motion"]["level"], "showreel")
        cleared = RD.apply_doc(self.p, {"motion_beats": {"levels": {}, "for": h}})
        self.assertEqual(cleared["changed"], ["s2"])
        self.assertNotIn("motion", seg(self.p, "s2"))

    def test_beat_map_matches_lines(self):
        bm = RD.beat_map(self.p)
        self.assertEqual(bm, {0: ["s1"], 1: ["s2"], 2: ["s3"]})


class SnipsUndoKeepsLooks(Base):
    def test_reset_rebuild_keeps_room_look(self):
        C.write_json(self.p / "work" / "edl.original.json", EDL)
        C.write_json(self.p / "work" / "snips_log.json", {"round": 1, "applied": ["a"], "ops": []})
        RD.apply_doc(self.p, {"beat_changes": [{"id": "x", "kind": "level", "seg": "s2", "level": "showreel"}]})
        self.quiet(SN.cmd_undo, self.p, [], self.out, reset=True)
        s2 = seg(self.p, "s2")
        self.assertEqual(s2["motion"]["level"], "showreel")
        self.assertEqual((s2["in"], s2["out"]), (3.0, 5.0))

    def test_reapply_without_log_is_noop(self):
        self.assertEqual(RD.reapply_looks(self.p, EDL), EDL)


class Cli(Base):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ENGINE / "rounds.py"), str(self.p), *args, "--json"],
                              capture_output=True, text=True, timeout=60)

    def test_cli_level_and_index(self):
        r = self.run_cli("level", "s1", "showreel")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["changed"], ["s1"])
        self.run_cli("snapshot")
        idx = json.loads(self.run_cli("index").stdout)
        self.assertEqual(idx["segs"]["s1"]["level"], "showreel")

    def test_cli_bad_round_exits_nonzero_with_plain_message(self):
        r = self.run_cli("use", "s2", "7")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no saved round 7", r.stdout)


if __name__ == "__main__":
    unittest.main()
