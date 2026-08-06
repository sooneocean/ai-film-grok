"""Unit tests for formal Real-ESRGAN upscale (mocked ncnn; no GPU required)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import media.realesrgan_upscale as ru  # noqa: E402


class RealEsrganUpscaleUnit(unittest.TestCase):
    def test_gpu_busy_env(self) -> None:
        import os

        with mock.patch.dict(os.environ, {"AIFILM_GPU_BUSY": "1"}, clear=False):
            os.environ.pop("AIFILM_I_OWN_THE_GPU", None)
            busy, reason = ru.gpu_busy()
            self.assertTrue(busy)
            self.assertEqual(reason, "AIFILM_GPU_BUSY")
        with mock.patch.dict(
            os.environ,
            {"AIFILM_I_OWN_THE_GPU": "1", "AIFILM_GPU_BUSY": "1"},
            clear=False,
        ):
            busy, reason = ru.gpu_busy()
            self.assertFalse(busy)
            self.assertEqual(reason, "i_own_the_gpu")

    def test_film_upscale_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(ru.film_upscale_enabled(root))
            (root / "film-spec.json").write_text(
                json.dumps({"upscale": {"enabled": True}}), encoding="utf-8"
            )
            self.assertTrue(ru.film_upscale_enabled(root))

    def test_run_batch_skips_when_gpu_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(ru, "gpu_busy", return_value=(True, "busy")):
                with mock.patch.object(
                    ru,
                    "plan_upscale",
                    return_value={
                        "ok": True,
                        "candidates": [
                            {
                                "shot_id": "s1",
                                "path": str(root / "x.mp4"),
                                "below_floor": True,
                            }
                        ],
                        "backend": {},
                        "gpu_busy": True,
                    },
                ):
                    rep = ru.run_upscale_batch(root, execute=True, max_items=1)
                    self.assertFalse(rep["ok"])
                    self.assertTrue(rep.get("gpu_busy_skipped"))

    def test_run_batch_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(
                ru,
                "plan_upscale",
                return_value={
                    "ok": True,
                    "candidates": [{"shot_id": "s1", "path": "/x.mp4"}],
                    "backend": {},
                    "gpu_busy": False,
                },
            ):
                rep = ru.run_upscale_batch(root, execute=False, max_items=3)
                self.assertTrue(rep["ok"])
                self.assertTrue(rep.get("dry_run"))
                self.assertEqual(rep["count"], 1)

    def test_promote_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_dir = root / "takes" / "_upscale"
            src_dir.mkdir(parents=True)
            src = src_dir / "s1_esrgan_s2.mp4"
            src.write_bytes(b"\x00\x00fake")
            with mock.patch.object(
                ru,
                "probe_media",
                return_value={
                    "path": str(src),
                    "width": 704,
                    "height": 1280,
                    "fps": 24,
                    "duration_sec": 1.0,
                    "has_audio": False,
                    "sha256": "abc",
                },
            ):
                rep = ru.promote_upscale(root, shot_id="s1")
            self.assertTrue(rep["ok"])
            self.assertTrue(Path(rep["promoted_path"]).is_file())
            self.assertFalse(rep.get("auto_register"))

    def test_plan_explicit_paths_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(
                ru,
                "probe_media",
                return_value={
                    "path": "/x.mp4",
                    "width": 352,
                    "height": 608,
                    "fps": 24,
                    "duration_sec": 1.0,
                    "has_audio": True,
                    "sha256": "x",
                },
            ):
                with mock.patch.object(
                    ru,
                    "backend_status",
                    return_value={"backend_ready": True},
                ):
                    rep = ru.plan_upscale(root, paths=["/x.mp4"])
            self.assertTrue(rep["ok"])
            self.assertEqual(rep["candidate_count"], 1)
            self.assertTrue(rep["candidates"][0]["below_floor"])


if __name__ == "__main__":
    unittest.main()
