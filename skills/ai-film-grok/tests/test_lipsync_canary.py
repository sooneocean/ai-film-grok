"""Tests for lipsync_canary.py — single-shot lipsync safety canary.

Previously had ZERO test coverage. Tests cover:
  - run_lipsync_canary: shot_id validation, no-backend path, missing media
  - receipt writing
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lipsync_canary import LipsyncCanaryError, run_lipsync_canary  # noqa: E402


class TestRunLipsyncCanary(unittest.TestCase):
    """run_lipsync_canary writes canary receipts."""

    def test_empty_shot_id_raises(self):
        """Empty shot_id → LipsyncCanaryError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LipsyncCanaryError) as ctx:
                run_lipsync_canary(Path(tmp), shot_id="", backend="auto")
            self.assertIn("shot_id", str(ctx.exception))

    def test_no_backend_ready_writes_receipt(self):
        """No locked backend → ok=False, next_unlock present, receipt written."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            mock_probe = mock.MagicMock(
                return_value={
                    "ready": [],
                    "wav2lip_root": "/fake/wav2lip",
                    "musetalk_root": None,
                    "backend_trust": {},
                }
            )
            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=mock_probe,
                        resolve_backend=lambda b: "off",
                        lipsync_one=lambda **kw: {"ok": False},
                    ),
                },
            ):
                report = run_lipsync_canary(root, shot_id="shot01")

            self.assertFalse(report["ok"])
            self.assertIsNotNone(report["next_unlock"])
            self.assertIn("error", report)
            # Receipt written
            self.assertTrue((root / "receipts" / "lipsync-canary.json").is_file())

    def test_missing_video_raises(self):
        """Backend ready but no video found → LipsyncCanaryError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": ["wav2lip"],
                            "wav2lip_root": "/w",
                            "musetalk_root": None,
                            "backend_trust": {},
                        },
                        resolve_backend=lambda b: "wav2lip",
                        lipsync_one=lambda **kw: {"ok": False},
                    ),
                },
            ):
                with self.assertRaises(LipsyncCanaryError) as ctx:
                    run_lipsync_canary(root, shot_id="shot01")
                self.assertIn("no video", str(ctx.exception))

    def test_missing_audio_raises(self):
        """Video present but no audio → LipsyncCanaryError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clips" / "shot01.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": ["wav2lip"],
                            "wav2lip_root": "/w",
                            "musetalk_root": None,
                            "backend_trust": {},
                        },
                        resolve_backend=lambda b: "wav2lip",
                        lipsync_one=lambda **kw: {"ok": False},
                    ),
                },
            ):
                with self.assertRaises(LipsyncCanaryError) as ctx:
                    run_lipsync_canary(root, shot_id="shot01", video=video)
                self.assertIn("no audio", str(ctx.exception))

    def test_backend_resolved_to_off_raises(self):
        """Backend resolves to off → LipsyncCanaryError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "shot.mp4"
            video.write_bytes(b"v")
            audio = root / "shot.wav"
            audio.write_bytes(b"a")

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": ["wav2lip"],
                            "wav2lip_root": "/w",
                            "musetalk_root": None,
                            "backend_trust": {},
                        },
                        resolve_backend=lambda b: "off",
                        lipsync_one=lambda **kw: {"ok": False},
                    ),
                },
            ):
                with self.assertRaises(LipsyncCanaryError) as ctx:
                    run_lipsync_canary(root, shot_id="shot01", video=video, audio=audio)
                self.assertIn("off", str(ctx.exception))

    def test_explicit_node_canary_allows_technical_ready_before_approval(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "shot.mp4"
            audio = root / "shot.wav"
            video.write_bytes(b"video")
            audio.write_bytes(b"audio")

            def fake_lipsync_one(**kwargs):
                self.assertTrue(kwargs["allow_unapproved"])
                kwargs["out"].write_bytes(b"candidate")
                return {"ok": True, "chosen_backend": "latentsync"}

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": [],
                            "node": {
                                "backends": {
                                    "latentsync": {
                                        "ready": False,
                                        "technical_ready": True,
                                    }
                                }
                            },
                        },
                        resolve_backend=mock.Mock(
                            side_effect=AssertionError("must bypass production resolver")
                        ),
                        lipsync_one=fake_lipsync_one,
                    ),
                },
            ):
                report = run_lipsync_canary(
                    root,
                    shot_id="shot01",
                    backend="latentsync",
                    video=video,
                    audio=audio,
                )

            self.assertTrue(report["ok"])
            self.assertEqual(report["backend_used"], "latentsync")

    def test_node_receipt_without_ok_flag_is_a_successful_canary(self):
        """The authenticated node returns a completed receipt, not ``ok=True``."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "shot.mp4"
            audio = root / "shot.wav"
            video.write_bytes(b"video")
            audio.write_bytes(b"audio")

            def fake_lipsync_one(**kwargs):
                kwargs["out"].write_bytes(b"candidate")
                return {"status": "completed", "chosen_backend": "musetalk"}

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": [],
                            "node": {
                                "backends": {"musetalk": {"ready": False, "technical_ready": True}}
                            },
                        },
                        resolve_backend=mock.Mock(
                            side_effect=AssertionError("must bypass production resolver")
                        ),
                        lipsync_one=fake_lipsync_one,
                    ),
                },
            ):
                report = run_lipsync_canary(
                    root,
                    shot_id="shot01",
                    backend="musetalk",
                    video=video,
                    audio=audio,
                )

            self.assertTrue(report["ok"])
            self.assertEqual(report["human_review"]["status"], "pending")

    def test_failed_node_receipt_never_promotes_an_output_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "shot.mp4"
            audio = root / "shot.wav"
            video.write_bytes(b"video")
            audio.write_bytes(b"audio")

            def fake_lipsync_one(**kwargs):
                kwargs["out"].write_bytes(b"stale candidate")
                return {"status": "failed", "chosen_backend": "musetalk"}

            with mock.patch.dict(
                sys.modules,
                {
                    "lipsync_backend": mock.MagicMock(
                        probe=lambda: {
                            "ready": [],
                            "node": {
                                "backends": {"musetalk": {"ready": False, "technical_ready": True}}
                            },
                        },
                        resolve_backend=mock.Mock(
                            side_effect=AssertionError("must bypass production resolver")
                        ),
                        lipsync_one=fake_lipsync_one,
                    ),
                },
            ):
                report = run_lipsync_canary(
                    root,
                    shot_id="shot01",
                    backend="musetalk",
                    video=video,
                    audio=audio,
                )

            self.assertFalse(report["ok"])
            self.assertNotIn("human_review", report)


if __name__ == "__main__":
    unittest.main()
