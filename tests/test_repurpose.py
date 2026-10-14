"""repurpose.py / repurpose_ops.py unit tests on synthetic frames:
python -m unittest tests/test_repurpose.py (from the repo root, with the Reel Room venv python)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import repurpose_ops as O  # noqa: E402

cv2 = O.cv2
W, H = 720, 1280
FONT = cv2.FONT_HERSHEY_DUPLEX if cv2 is not None else None


def background(seed=1):
    """gray wall: smooth vertical + horizontal gradient with light seeded noise"""
    y = np.linspace(70, 110, H, dtype=np.float32)[:, None]
    x = np.linspace(-8, 8, W, dtype=np.float32)[None, :]
    g = y + x + np.random.default_rng(seed).normal(0, 1.5, (H, W)).astype(np.float32)
    return np.clip(np.repeat(g[..., None], 3, axis=2), 0, 255).astype(np.uint8)


def caption(img, text, x, y, scale=1.1, colour=(255, 255, 255)):
    """burned-in caption: dark stroke then a white (or yellow) fill. Returns a new frame."""
    out = img.copy()
    cv2.putText(out, text, (x, y), FONT, scale, (8, 8, 8), 7, cv2.LINE_AA)
    cv2.putText(out, text, (x, y), FONT, scale, colour, 2, cv2.LINE_AA)
    return out


def changed_box(a, b, thr=12):
    ys, xs = np.nonzero(np.abs(a.astype(int) - b.astype(int)).max(-1) > thr)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def mad(a, b, box):
    x0, y0, x1, y1 = box
    return float(np.abs(a[y0:y1, x0:x1].astype(np.float32) - b[y0:y1, x0:x1].astype(np.float32)).mean())


def outside_equal(a, b, box, margin):
    m = np.ones(a.shape[:2], bool)
    x0, y0, x1, y1 = O.clip_box(O.grow_box(box, margin), a.shape[1], a.shape[0])
    m[y0:y1, x0:x1] = False
    return bool((a[m] == b[m]).all())


@unittest.skipIf(cv2 is None, "OpenCV not installed (use the Reel Room venv python)")
class Detect(unittest.TestCase):
    def setUp(self):
        self.bg = background()
        self.img = caption(self.bg, "THIS IS THE OLD CAPTION", 140, 990)
        self.truth = changed_box(self.bg, self.img)

    def test_caption_extent_finds_x_range(self):
        ex = O.caption_extent(self.img, int(0.72 * H), int(0.82 * H))
        self.assertIsNotNone(ex)
        self.assertLessEqual(abs(ex[0] - self.truth[0]), 8)
        self.assertLessEqual(abs(ex[1] - self.truth[2]), 8)

    def test_caption_extent_none_on_clean_frame(self):
        self.assertIsNone(O.caption_extent(self.bg, int(0.72 * H), int(0.82 * H)))

    def test_caption_extent_ignores_big_white_area(self):
        img = self.img.copy()
        img[930:1050, 600:720] = 250  # a white chair at the edge
        img[930:1050, 590:600] = 5
        ex = O.caption_extent(img, int(0.72 * H), int(0.82 * H))
        self.assertLessEqual(abs(ex[1] - self.truth[2]), 8)

    def test_find_band_covers_caption_rows(self):
        rows = np.zeros(H)
        rows[:] = O.thin_text(self.img, colour=False).sum(1)
        y0, y1 = O.find_band(rows, H)
        self.assertLessEqual(y0, self.truth[1])
        self.assertGreaterEqual(y1, self.truth[3])
        self.assertLess(y1 - y0, 120)

    def test_glyph_mask_covers_static_title(self):
        frames = [caption(background(s), "OLD TITLE", 200, 200, 1.6) for s in range(6)]
        m = O.glyph_mask(frames, [150, 140, 600, 230])
        diff = np.abs(frames[0].astype(int) - background(0).astype(int)).max(-1) > 20
        self.assertGreater((m[diff] > 0).mean(), 0.97)
        self.assertEqual(int(m[600:].sum()), 0)

    def test_static_windows_split_titles(self):
        a = np.zeros((40, 80), bool)
        a[5:15, 5:40] = True
        b = np.zeros((40, 80), bool)
        b[20:30, 30:70] = True
        samples = [(f, a) for f in range(0, 30, 3)] + [(f, b) for f in range(30, 60, 3)]
        wins = O.static_windows(samples, 3)
        self.assertEqual([(w[0], w[1]) for w in wins], [(0, 29), (30, 59)])
        self.assertTrue(wins[0][2][10, 10] and not wins[0][2][25, 50])

    def test_track_boxes_links_overlapping_boxes(self):
        card = [50, 600, 670, 880]
        samples = [(f, [card] if 30 <= f < 90 else []) for f in range(0, 120, 6)]
        self.assertEqual(O.track_boxes(samples, 6), [(30, 89, card)])

    def test_card_candidates_finds_dark_card(self):
        img = self.bg.copy()
        img[600:880, 50:670] = (20, 14, 18)
        for k, line in enumerate(("17,604 adults with", "overweight or obesity", "No diabetes")):
            cv2.putText(img, line, (80, 660 + 60 * k), FONT, 1.0, (250, 250, 250), 2, cv2.LINE_AA)
        boxes = O.card_candidates(img, 940)
        self.assertEqual(len(boxes), 1)
        x0, y0, x1, y1 = boxes[0]
        self.assertLessEqual(abs(x0 - 50), 6)
        self.assertLessEqual(abs(x1 - 670), 6)
        self.assertLessEqual(abs(y0 - 600), 4)
        self.assertGreaterEqual(y1, 840)


@unittest.skipIf(cv2 is None, "OpenCV not installed (use the Reel Room venv python)")
class Methods(unittest.TestCase):
    def setUp(self):
        self.bg = background()
        self.img = caption(self.bg, "OLD CAPTION TEXT", 160, 990)
        self.box = O.grow_box(changed_box(self.bg, self.img), 4)
        self.before = mad(self.img, self.bg, self.box)

    def check(self, out, limit, margin):
        after = mad(out, self.bg, self.box)
        self.assertLess(after, limit, f"text area still differs from the clean wall: {after:.1f}")
        self.assertLess(after, 0.5 * self.before)
        self.assertTrue(outside_equal(out, self.img, self.box, margin), "pixels outside the region changed")

    def test_blur(self):
        out = O.op_blur(self.img, self.box, tint=0.0, feather=18)
        self.check(out, 12, 19)

    def test_blur_interior_has_no_text_contrast(self):
        out = O.op_blur(self.img, self.box, tint=0.4, feather=18)
        x0, y0, x1, y1 = self.box
        g = out[y0:y1, x0:x1].astype(np.float32).mean(-1)
        self.assertLess(float(np.abs(np.diff(g, axis=1)).max()), 6)

    def test_inpaint_with_glyph_mask(self):
        mask = O.glyph_mask([self.img, self.img, self.img], self.box)
        out = O.op_inpaint(self.img, self.box, mask, seed=3)
        self.check(out, 6, 60)

    def test_inpaint_whole_box(self):
        out = O.op_inpaint(self.img, self.box, None, seed=3)
        self.check(out, 6, 60)

    def test_ref(self):
        out = O.op_ref(self.img, self.box, self.bg, feather=8)
        self.check(out, 2, 9)

    def test_interp(self):
        out = O.op_interp(self.img, self.box, seed=1, noise=1.0)
        self.check(out, 5, 1)

    def test_apply_region_per_frame_and_errors(self):
        r = {"id": "c", "method": "ref", "box": [0, self.box[1], W, self.box[3]], "frames": "all",
             "per_frame": {"4": [self.box[0], self.box[2]]}}
        self.assertIs(O.apply_region(self.img, r, 3, 10, {"ref": self.bg}), self.img)
        out = O.apply_region(self.img, r, 4, 10, {"ref": self.bg})
        self.assertLess(mad(out, self.bg, self.box), 2)
        with self.assertRaises(ValueError):
            O.apply_region(self.img, r, 4, 10, {})
        with self.assertRaises(ValueError):
            O.apply_region(self.img, {**r, "method": "smudge"}, 4, 10, {"ref": self.bg})


class Parsing(unittest.TestCase):
    def test_parse_range(self):
        self.assertEqual(O.parse_range("all", 100), (0, 99))
        self.assertEqual(O.parse_range(None, 100), (0, 99))
        self.assertEqual(O.parse_range([10, 20], 100), (10, 20))
        self.assertEqual(O.parse_range("5-9", 100), (5, 9))
        self.assertEqual(O.parse_range("7", 100), (7, 7))
        self.assertEqual(O.parse_range([90, 500], 100), (90, 99))
        for bad in ("a-b", "1-2-3", [20, 10]):
            with self.assertRaises(ValueError):
                O.parse_range(bad, 100)

    def test_region_box_frames_pad_and_per_frame(self):
        r = {"box": [100, 900, 600, 960], "frames": [10, 20], "pad": 5}
        self.assertIsNone(O.region_box(r, 9, 100, W, H))
        self.assertEqual(O.region_box(r, 10, 100, W, H), (95, 895, 605, 965))
        pf = {"box": [0, 900, W, 960], "frames": "all", "per_frame": {"3": [200, 400]}}
        self.assertEqual(O.region_box(pf, 3, 100, W, H), (200, 900, 400, 960))
        self.assertIsNone(O.region_box(pf, 4, 100, W, H))

    def test_hex_bgr(self):
        self.assertEqual(O.hex_bgr("#102030").tolist(), [48, 32, 16])
        with self.assertRaises(ValueError):
            O.hex_bgr("#12")


class Crop(unittest.TestCase):
    REGS = [{"id": "title", "kind": "title", "box": [90, 100, 630, 280]},
            {"id": "captions", "kind": "caption", "box": [110, 940, 610, 990]},
            {"id": "card1", "kind": "card", "box": [50, 600, 670, 880]}]

    def test_excludes_bands_and_keeps_9x16(self):
        p = O.crop_plan(720, 1280, self.REGS)
        x0, y0, x1, y1 = p["box"]
        self.assertGreaterEqual(y0, 280)
        self.assertLessEqual(y1, 940)
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), 9 / 16, delta=0.01)
        self.assertGreater(p["zoom"], 1.0)
        self.assertAlmostEqual(p["upscale"], 1920 / (y1 - y0), delta=0.02)
        self.assertEqual(p["uncovered"], ["card1"])

    def test_title_only_keeps_bottom(self):
        p = O.crop_plan(720, 1280, self.REGS[:1])
        self.assertEqual(p["box"][3], 1280)
        self.assertGreaterEqual(p["box"][1], 280)

    def test_wide_source_is_width_limited_when_needed(self):
        p = O.crop_plan(1920, 1080, [{"id": "t", "kind": "title", "box": [0, 0, 1920, 120]}])
        self.assertGreaterEqual(p["box"][1], 120)
        self.assertAlmostEqual(p["w"] / p["h"], 9 / 16, delta=0.01)

    def test_refuses_when_bands_leave_too_little(self):
        regs = [{"id": "t", "kind": "title", "box": [0, 0, 720, 520]},
                {"id": "c", "kind": "caption", "box": [0, 800, 720, 1280]}]
        with self.assertRaises(ValueError):
            O.crop_plan(720, 1280, regs)


@unittest.skipIf(cv2 is None or shutil.which("ffmpeg") is None, "needs OpenCV and ffmpeg")
class BakeCli(unittest.TestCase):
    """end to end on a tiny synthetic video: bake a frame range, check frame count and that the caption is gone"""

    def test_bake_range(self):
        import repurpose as R
        tmp = Path(tempfile.mkdtemp())
        try:
            src = tmp / "src.mp4"
            bg = cv2.resize(background(), (360, 640))
            img = caption(bg, "OLD CAPTION", 80, 500, 0.6)
            vw = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 30, (360, 640))
            if not vw.isOpened():
                self.skipTest("cv2 cannot write mp4v here")
            for _ in range(12):
                vw.write(img)
            vw.release()
            box = O.grow_box(changed_box(bg, img), 4)
            regs = tmp / "r.json"
            regs.write_text(json.dumps({"regions": [{"id": "c", "method": "blur", "box": box, "frames": "all",
                                                     "tint": 0.0}]}))
            out = tmp / "out.mp4"
            argv = ["repurpose.py", "bake", str(src), str(regs), str(out), "--frames", "2-9", "--size", "360x640",
                    "--check", str(tmp / "c.jpg"), "--json"]
            old, sys.argv = sys.argv, argv
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    R.main()
            finally:
                sys.argv = old
            res = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(res["frames"], 8)
            self.assertTrue((tmp / "c.jpg").exists())
            cap = cv2.VideoCapture(str(out))
            ok, f = cap.read()
            cap.release()
            self.assertTrue(ok)
            self.assertLess(mad(f, bg, box), 0.5 * mad(img, bg, box))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
