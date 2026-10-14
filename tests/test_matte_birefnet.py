"""matte_birefnet.py unit tests (no model, no ffmpeg): python -m unittest tests/test_matte_birefnet.py (repo root)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "skills" / "reel" / "engine"
sys.path.insert(0, str(ENGINE))

import matte_birefnet as MB  # noqa: E402


def disc_alpha(h=64, w=64, r=18, cx=32, cy=32):
    yy, xx = np.mgrid[0:h, 0:w]
    return (((yy - cy) ** 2 + (xx - cx) ** 2) <= r * r).astype(np.float32)


class Finalize(unittest.TestCase):
    def test_alpha_stays_in_range(self):
        rng = np.random.default_rng(1)
        img = rng.random((48, 48, 3), dtype=np.float32)
        al = np.clip(disc_alpha(48, 48, 14, 24, 24) + rng.normal(0, 0.3, (48, 48)).astype(np.float32), -0.5, 1.5)
        out = MB.feather(MB.erode(al.astype(np.float32)))
        self.assertGreaterEqual(out.min(), 0.0)
        self.assertLessEqual(out.max(), 1.0)
        rgba = MB.clean_frame(None, (img, img.mean(axis=2), np.clip(al, 0, 1).astype(np.float32)), None)
        self.assertEqual(rgba.dtype, np.uint8)
        self.assertEqual(rgba.shape, (48, 48, 4))

    def test_erode_shrinks(self):
        al = disc_alpha()
        er = MB.erode(al, 1)
        self.assertLess(er.sum(), al.sum())
        self.assertTrue(np.all(er <= al))
        self.assertTrue(np.array_equal(MB.erode(al, 0), al))

    def test_feather_softens_edge(self):
        al = disc_alpha()
        fe = MB.feather(al, 0.8)
        self.assertTrue(((fe > 0.01) & (fe < 0.99)).sum() > ((al > 0.01) & (al < 0.99)).sum())

    def test_despill_does_not_brighten_edge_above_interior(self):
        h = w = 64
        core = disc_alpha(h, w, 16)
        ring = disc_alpha(h, w, 20) - core
        al = (core + ring * 0.5).astype(np.float32)
        fg = np.full((h, w, 3), 0.4, np.float32)                 # interior: mid grey subject
        fg[ring > 0] = 1.0                                       # edge band: white background spill
        out = MB.despill(fg, al)
        lum = out.mean(axis=2)
        interior = lum[core > 0].mean()
        self.assertLessEqual(lum[ring > 0].max(), interior * 1.08 + 1e-3)
        self.assertTrue(np.allclose(out[core > 0], fg[core > 0], atol=1e-4))

    def test_estimate_fg_recovers_subject_colour(self):
        h = w = 64
        al = MB.feather(disc_alpha(h, w, 18), 2.0)
        F, B = np.array([0.8, 0.2, 0.1], np.float32), np.array([0.1, 0.3, 0.9], np.float32)
        img = (al[..., None] * F + (1 - al[..., None]) * B).astype(np.float32)
        fg = MB.estimate_fg(img, al)
        edge = (al > 0.3) & (al < 0.7)
        err_fg = np.abs(fg[edge] - F).mean()
        err_img = np.abs(img[edge] - F).mean()
        self.assertLess(err_fg, err_img * 0.5)

    def test_temporal_smoothing_skipped_where_plate_moves(self):
        h, w = 40, 80
        a_prev, a_next = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
        a = np.ones((h, w), np.float32)                           # flicker: on at t, off at t-1 and t+1
        g = np.full((h, w), 0.5, np.float32)
        g_prev, g_next = g.copy(), g.copy()
        g_prev[:, 40:] = 0.0                                      # right half of the plate moves
        g_next[:, 40:] = 1.0
        out = MB.temporal_smooth(a_prev, a, a_next, g_prev, g, g_next)
        self.assertTrue(np.allclose(out[:, :30], 0.0, atol=1e-3))  # static: median of 0, 1, 0
        self.assertTrue(np.allclose(out[:, 50:], 1.0, atol=1e-3))  # moving: untouched
        self.assertGreaterEqual(out.min(), 0.0)
        self.assertLessEqual(out.max(), 1.0)

    def test_windows(self):
        got = list(MB.windows(iter([1, 2, 3])))
        self.assertEqual(got, [(None, 1, 2), (1, 2, 3), (2, 3, None)])
        self.assertEqual(list(MB.windows(iter([7]))), [(None, 7, None)])
        self.assertEqual(list(MB.windows(iter([]))), [])


class Interpreter(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="rr-biref-"))
        self.default = str(self.home / "birefnet" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_order_env_platform_default(self):
        (self.home / "platform.json").write_text(json.dumps({"birefnet_py": "/p/plat"}))
        c = MB.python_candidates({"REEL_ROOM_BIREFNET_PY": "/p/env"}, self.home)
        self.assertEqual([p for _, p in c], ["/p/env", "/p/plat", self.default])

    def test_env_wins(self):
        py = MB.resolve_python({"REEL_ROOM_BIREFNET_PY": "/p/env"}, self.home, check=lambda p: True)
        self.assertEqual(py, "/p/env")

    def test_falls_through_to_platform_then_default(self):
        (self.home / "platform.json").write_text(json.dumps({"birefnet_py": "/p/plat"}))
        env = {"REEL_ROOM_BIREFNET_PY": "/p/broken"}
        self.assertEqual(MB.resolve_python(env, self.home, check=lambda p: p == "/p/plat"), "/p/plat")
        self.assertEqual(MB.resolve_python({}, self.home, check=lambda p: p == self.default), self.default)

    def test_bad_platform_json_is_ignored(self):
        (self.home / "platform.json").write_text("{not json")
        self.assertEqual([p for _, p in MB.python_candidates({}, self.home)], [self.default])

    def test_none_works_gives_setup_commands(self):
        with self.assertRaises(RuntimeError) as cm:
            MB.resolve_python({}, self.home, check=lambda p: False)
        msg = str(cm.exception)
        self.assertIn("python3 -m venv ~/.reel-room/birefnet", msg)
        self.assertIn("pip install torch transformers timm kornia einops pillow numpy", msg)
        self.assertIn("REEL_ROOM_BIREFNET_PY", msg)

    def test_missing_file_is_not_usable(self):
        self.assertFalse(MB.has_torch(str(self.home / "nope" / "python")))


class CacheAndParts(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="rr-biref-"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def fake_cache(self, root):
        hub = root / "hub"
        snap = hub / MB.MODEL_DIR / "snapshots" / "abc"
        snap.mkdir(parents=True)
        (hub / "blobs" / "99").mkdir(parents=True)
        (hub / "blobs" / "99" / "w").write_bytes(b"weights")
        (hub / MB.MODEL_DIR / "blobs").mkdir()
        os.symlink("../../blobs/99/w", hub / MB.MODEL_DIR / "blobs" / "sha")
        os.symlink("../../blobs/sha", snap / "model.safetensors")
        (root / "modules" / "m").mkdir(parents=True)
        (root / "modules" / "m" / "x.py").write_text("x = 1\n")
        return root

    @unittest.skipIf(os.name == "nt", "symlinks need admin on Windows")
    def test_seed_cache_copies_model_and_shared_blobs(self):
        src = self.fake_cache(self.d / "src")
        dst = MB.seed_cache(src, self.d / "dst")
        self.assertTrue(MB.model_cached(dst))
        snap = dst / "hub" / MB.MODEL_DIR / "snapshots" / "abc" / "model.safetensors"
        self.assertEqual(snap.read_bytes(), b"weights")
        self.assertTrue((dst / "modules" / "m" / "x.py").is_file())

    def test_seed_cache_missing_model_errors(self):
        with self.assertRaises(RuntimeError):
            MB.seed_cache(self.d / "empty", self.d / "dst")

    def test_infer_env_defaults(self):
        e = MB.infer_env({"HF_HOME": str(self.d)})
        self.assertEqual(e["HF_HOME"], str(self.d))
        self.assertNotIn("HF_HUB_OFFLINE", e)
        self.assertEqual(e["PYTHONDONTWRITEBYTECODE"], "1")

    def test_model_res(self):
        self.assertEqual(MB.model_res("fast", 1080, 1920), (1024, 576))
        self.assertEqual(MB.model_res("best", 1080, 1920), (2048, 1152))
        self.assertEqual(MB.model_res("balanced", 1920, 1080), (864, 1536))
        for hh, ww in MB.QUALITY_RES.values():
            self.assertEqual((hh % 32, ww % 32), (0, 0))
        with self.assertRaises(RuntimeError):
            MB.model_res("ultra", 1080, 1920)

    def test_parts_resume_and_invalidate(self):
        src = self.d / "aroll.mp4"
        src.write_bytes(b"x" * 10)
        parts = str(self.d / "matte_alpha")
        MB.prepare_parts(parts, str(src), (1024, 576))
        for k in (0, 1, 3):
            Path(MB.part_path(parts, k)).write_bytes(b"p")
        Path(MB.part_path(parts, 4, tmp=True)).write_bytes(b"t")
        MB.prepare_parts(parts, str(src), (1024, 576))
        self.assertEqual(MB.completed_parts(parts), 2)            # gap at 2: 3 is redone
        self.assertFalse(os.path.exists(MB.part_path(parts, 4, tmp=True)))
        MB.prepare_parts(parts, str(src), (2048, 1152))           # new model size: start over
        self.assertEqual(MB.completed_parts(parts), 0)


if __name__ == "__main__":
    unittest.main()
