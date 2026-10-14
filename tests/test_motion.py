"""Motion v2 unit tests (no render, no ffmpeg): python -m unittest tests/test_motion.py (from the repo root)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "skills", "reel", "engine")
sys.path.insert(0, os.path.join(ENGINE, "motion"))
sys.path.insert(0, ENGINE)

import motion as M  # noqa: E402
import mixer  # noqa: E402
import qa_motion as QM  # noqa: E402

WORDS = [{"text": t, "start": s, "end": s + 0.25} for t, s in
         [("so", 0.1), ("the", 0.4), ("first", 0.7), ("part", 1.0), ("is", 1.3), ("tolerance.", 1.6),
          ("this", 3.0), ("is", 3.3), ("tolerance", 3.6), ("again", 6.0)]]


def shot(t0, t1, seg, layout="card"):
    return {"t0": t0, "t1": t1, "seg": seg, "layout": layout, "visible": True, "ox": 540, "oy": 800, "face_h": 200}


class Config(unittest.TestCase):
    def test_defaults(self):
        c = M.config({})
        self.assertEqual((c["level"], c["sfx"], c["grain"]), ("polished", "light", False))

    def test_levels_and_overrides(self):
        self.assertEqual(M.config({"motion": {"level": "simple"}})["transitions"], "off")
        self.assertEqual(M.config({"motion": {"level": "showreel"}})["transitions"], "every-cut")
        c = M.config({"motion": {"transitions": {"per10s": 2, "moves": ["whip", "nope"]}}})
        self.assertEqual((c["per10s"], c["moves"]), (2.0, ["whip"]))
        self.assertEqual(M.config({"motion": {"level": "bogus", "sfx": "loud"}})["level"], "polished")

    def test_ease_upgrade(self):
        pol, simple = M.config({}), M.config({"motion": {"level": "simple"}})
        self.assertEqual(M.upgrade_ease("power3.out", pol), "expo.out")
        self.assertEqual(M.upgrade_ease("power2.in", pol), "expo.out")
        self.assertEqual(M.upgrade_ease("back.out(1.6)", pol), "back.out(1.6)")
        self.assertEqual(M.upgrade_ease("power3.out", simple), "power3.out")


class Words(unittest.TestCase):
    def test_ordered_search_and_lead(self):
        cur = M.WordCursor(WORDS)
        self.assertAlmostEqual(cur.at("@tolerance", lead="none"), 1.6)
        self.assertAlmostEqual(cur.at("@tolerance", lead="visual"), 3.6 - 0.04)   # searched AFTER the first one

    def test_fallback(self):
        cur = M.WordCursor(WORDS, start=3.0)
        self.assertAlmostEqual(cur.at("@missing", fallback=0.5, lead="none"), 3.5)


class Transitions(unittest.TestCase):
    def test_keys_cover_and_rest(self):
        for move in ("whip", "zoom", "drop", "push", "smash"):
            keys, span = M.transition_keys(move, 300, 1.0)
            rows = keys["T"]
            self.assertEqual(rows[-1][1:], [1.0, 0.0, 0.0, 0.0, 0.0, 0.0], move)   # clean identity after the move
            for f, s, x, y, r, _bx, _by in rows:
                self.assertGreaterEqual(s + 1e-6, M.cover(x, y, r, *M.T_ORIGIN), move)
            self.assertEqual(span[1], 300 + M.MOVES[move]["inn"])

    def test_iris_and_flash(self):
        k, _ = M.transition_keys("iris", 90, 1.0, point=(500, 800))
        self.assertEqual(k["iris"][-1][1], 0)          # plate hidden at the end
        k, _ = M.transition_keys("flash", 90, 1.0)
        self.assertEqual(k["flash"][-1][1], 0.0)

    def test_budget(self):
        cuts = [{"t": t, "section": True, "visible": True, "into": f"s{i}", "point": None}
                for i, t in enumerate([1.0, 2.0, 3.0, 6.0, 9.5])]
        shots = [shot(a, b, f"s{i}") for i, (a, b) in enumerate(zip([0, 1, 2, 3, 6, 9.5], [1, 2, 3, 6, 9.5, 12]))]
        p = M.plan(frames=360, cuts=cuts, shots=shots, words=WORDS, cfg=M.config({}), log=lambda *_: None)
        ts = [t["t"] for t in p["transitions"]]
        self.assertTrue(all(b - a >= 10 / 3.4 - 1e-6 for a, b in zip(ts, ts[1:])), ts)
        simple = M.plan(frames=360, cuts=cuts, shots=shots, words=WORDS, cfg=M.config({"motion": {"level": "simple"}}),
                        log=lambda *_: None)
        self.assertEqual(simple["transitions"], [])


    def test_unknown_override_never_crashes(self):
        cuts = [{"t": 2.0, "section": True, "visible": True, "into": "b", "point": None, "override": {"transition": "wipe"}}]
        shots = [shot(0, 2, "a"), shot(2, 4, "b")]
        for lvl in ("simple", "polished"):
            p = M.plan(frames=120, cuts=cuts, shots=shots, words=WORDS, cfg=M.config({"motion": {"level": lvl}}),
                       log=lambda *_: None)
            self.assertTrue(all(t["move"] in M.MOVES for t in p["transitions"]))

    def test_override_is_tagged_and_free_of_budget(self):
        cuts = [{"t": t, "section": False, "visible": True, "into": f"s{t}", "point": None, "override": {"transition": "whip"}}
                for t in (1.0, 2.0)]
        shots = [shot(0, 1, "s0"), shot(1, 2, "s1.0"), shot(2, 4, "s2.0")]
        p = M.plan(frames=120, cuts=cuts, shots=shots, words=WORDS, cfg=M.config({"motion": {"transitions": "off"}}),
                   log=lambda *_: None)
        self.assertEqual(len(p["transitions"]), 2)
        self.assertTrue(all(t.get("override") for t in p["transitions"]))
        self.assertTrue(QM.check_transition_budget(p, 4.0)["pass"])


class Camera(unittest.TestCase):
    def test_fillers_break_long_stills(self):
        shots = [shot(0, 8, "a")]
        p = M.plan(frames=240, cuts=[], shots=shots, words=WORDS, cfg=M.config({}), alive=[0] * 240, log=lambda *_: None)
        ev = sorted([0.0] + [r["t"] for r in p["reframes"]] + [x["t"] for x in p["punches"]] + [8.0])
        self.assertTrue(max(b - a for a, b in zip(ev, ev[1:])) < 1.6, ev)
        fil = sorted([r["t"] for r in p["reframes"]] + [x["t"] for x in p["punches"] if x["word"] == "(filler)"])
        self.assertTrue(all(b - a >= 1.2 - 1e-6 for a, b in zip(fil, fil[1:])), fil)

    def test_live_plate_needs_no_fillers(self):
        p = M.plan(frames=240, cuts=[], shots=[shot(0, 8, "a")], words=WORDS, cfg=M.config({}), alive=[1] * 240,
                   log=lambda *_: None)
        self.assertEqual(p["reframes"], [])

    def test_camera_never_below_one_and_deterministic(self):
        cfg = M.config({"motion": {"level": "showreel"}})
        a = M.plan(frames=120, cuts=[], shots=[shot(0, 4, "a")], words=WORDS, cfg=cfg, log=lambda *_: None)
        b = M.plan(frames=120, cuts=[], shots=[shot(0, 4, "a")], words=WORDS, cfg=cfg, log=lambda *_: None)
        self.assertEqual(a["camera"], b["camera"])
        self.assertTrue(all(r[1] >= 1.0 for r in a["camera"]))
        s, x, y, r, ox, oy = M.camera_at(a, 60)
        self.assertGreaterEqual(s, M.cover(x, y, r, ox, oy) - 1e-3)


class BeatLevels(unittest.TestCase):
    """rounds.py writes edl segments[i].motion = {level, transition?, camera?, from_level}: a Simple beat inside a
    Showreel reel stays calm, and the gates judge it by its own thresholds."""
    SIMPLE = {"level": "simple", "transition": "none", "camera": "still", "from_level": ["camera", "transition"]}

    def _plan(self, mid_override):
        cfg = M.config({"motion": {"level": "showreel"}})
        shots = [dict(shot(0, 3, "a"), override={}), dict(shot(3, 6, "b"), override=mid_override),
                 dict(shot(6, 9, "c"), override={})]
        cuts = [{"t": 3.0, "section": False, "visible": True, "into": "b", "override": mid_override,
                 "level": mid_override.get("level"), "point": [540, 800]},
                {"t": 6.0, "section": False, "visible": True, "into": "c", "override": {}, "point": [540, 800]}]
        words = [{"text": w, "start": t, "end": t + 0.3} for t, w in zip([x * 0.5 for x in range(1, 18)], ["tolerance"] * 17)]
        return M.plan(frames=270, cuts=cuts, shots=shots, words=words, accents=["tolerance"], cfg=cfg,
                      alive=[0] * 270, log=lambda *_: None)

    def test_simple_beat_stays_calm(self):
        p = self._plan(self.SIMPLE)
        self.assertEqual([t["into"] for t in p["transitions"]], ["c"])          # nothing cuts INTO the simple beat
        self.assertFalse([x for x in p["punches"] if x["shot"] == "b"])
        self.assertFalse([x for x in p["reframes"] if x["shot"] == "b"])
        rows = [r for r in p["camera"] if 90 <= r[0] < 180]
        self.assertTrue(rows and all(r[1] <= 1.031 and r[2] == 0 and r[3] == 0 for r in rows))   # settle only, no drift
        self.assertTrue([x for x in p["punches"] if x["shot"] in ("a", "c")])   # the showreel beats still move
        self.assertIn([3.0, 6.0, "simple"], p["levels"])
        self.assertEqual(M.level_at(p, 4.0), "simple")
        self.assertIsNone(M.caption_kind("tolerance", {"tolerance"}, M.for_level(M.config({"motion": {"level": "showreel"}}), "simple")))

    def test_explicit_override_beats_the_level(self):
        p = self._plan({"level": "simple", "camera": "close", "transition": "whip"})
        self.assertTrue([r for r in p["reframes"] if r["shot"] == "b" and r["close"]])
        self.assertIn("b", [t["into"] for t in p["transitions"]])

    def test_gates_use_the_beats_own_thresholds(self):
        cfg, pj = M.config({"motion": {"level": "showreel"}}), {"motion": {"level": "showreel"}}
        groups = QM.level_groups([[0, 3, "showreel"], [3, 6, "simple"], [6, 9, "showreel"]], cfg, pj)
        calm = {"stills": [(3.5, 4.5)], "longest_still_s": 1.0}
        self.assertTrue(QM.check_dead_frames_levels(calm, groups)["pass"])      # 1 s still inside Simple: exempt
        busy = {"stills": [(6.5, 7.5)], "longest_still_s": 1.0}
        self.assertFalse(QM.check_dead_frames_levels(busy, groups)["pass"])     # same still inside Showreel: > 0.8 s
        d = [9.0] * 45 + [0.5] * 45 + [9.0] * 45                                  # 15 fps: still only in the simple span
        m = {"d": d, "persec": [1] * 9}
        self.assertTrue(QM.check_motion_density_levels(m, groups)["pass"])


class Mixer(unittest.TestCase):
    EV = ([{"t": 1.0 + i * 0.4, "kind": "pop"} for i in range(20)] +
          [{"t": 2.0, "kind": "transition", "sound": "whoosh", "src": "motion"},
           {"t": 3.0, "kind": "punch", "src": "motion"}])

    def test_light_is_sparse(self):
        p = mixer.pick(self.EV, "light", 30)
        self.assertTrue(all(b["t"] - a["t"] >= 1.5 for a, b in zip(p, p[1:])))
        self.assertTrue(any(x["transition"] for x in p))
        self.assertFalse(any(x["kind"] == "punch" for x in p))     # camera moves are silent

    def test_full_and_off(self):
        self.assertGreater(len(mixer.pick(self.EV, "full", 30)), len(mixer.pick(self.EV, "light", 30)))
        self.assertEqual(mixer.pick(self.EV, "off", 30), [])
        self.assertTrue(all(x["transition"] for x in mixer.pick(self.EV, "full", 30, include_inserts=False)))


class Gates(unittest.TestCase):
    def test_ease_lint(self):
        html = ('<div id="h" data-hero="1"></div><script>tl.fromTo("#a",{"opacity":0,"y":20},{"opacity":1,"ease":"power2.in"},1);'
                'tl.fromTo("#b",{"opacity":0,"y":20},{"opacity":1,"ease":"expo.out"},1);'
                'tl.fromTo("#h",{"opacity":0},{"opacity":1,"ease":"expo.out"},1);</script>')
        r = QM.ease_lint(html)
        self.assertEqual(r["entrances"], 3)
        self.assertEqual(len(r["bad"]), 1)
        self.assertEqual(len(r["opacity_only_hero"]), 1)

    def test_hero_scale(self):
        tg = M.LEVELS["polished"]["targets"]
        ok = QM.check_hero_scale([{"t0": 0, "t1": 1, "layout": "media", "boxes": [{"kind": "card", "x": 0, "y": 0, "w": 100, "h": 10}]}], tg)
        self.assertTrue(ok["pass"])
        bad = QM.check_hero_scale([{"t0": 0, "t1": 1, "boxes": [{"kind": "card", "x": 0, "y": 0, "w": 300, "h": 10}]}], tg)
        self.assertFalse(bad["pass"])
        self.assertTrue(QM.check_hero_scale([], M.LEVELS["simple"]["targets"]).get("skipped"))

    def test_behind_head(self):
        good = {"behind": [{"text": "FORTITUDE", "t0": 1, "chars": 9, "box": [100, 500, 900, 200], "head": [450, 650, 180, 300]}]}
        bad = {"behind": [{"text": "FORT", "t0": 1, "chars": 4, "box": [400, 500, 280, 200], "head": [400, 600, 280, 300]}]}
        self.assertTrue(QM.check_behind_head(good)["pass"])
        self.assertFalse(QM.check_behind_head(bad)["pass"])

    def test_dead_frames_levels(self):
        m = {"longest_still_s": 1.5, "stills": [(2.0, 3.5)], "mean_motion": 5, "pct_frames_active": 60, "persec": [1, 2]}
        self.assertFalse(QM.check_dead_frames(m, M.LEVELS["polished"]["targets"])["pass"])
        self.assertTrue(QM.check_dead_frames(m, M.LEVELS["simple"]["targets"])["pass"])


if __name__ == "__main__":
    unittest.main()
