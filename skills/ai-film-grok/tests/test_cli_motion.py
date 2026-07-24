"""Tests for cli_motion.py — media-generation CLI routes.

Previously had ZERO test coverage. Tests cover:
  - env_plate route: prompt validation, prompt-file reading, arg forwarding
  - motion_plan route: arg forwarding, error wrapping
  - MotionRouteError wrapping
"""

from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_motion import MotionRouteError, env_plate, motion_plan  # noqa: E402


class TestEnvPlateRoute(unittest.TestCase):
    """env_plate route validates prompt and forwards to run_env_plate."""

    def test_empty_prompt_raises(self):
        """No prompt → MotionRouteError."""
        args = Namespace(prompt="", prompt_file=None, root=None)
        with self.assertRaises(MotionRouteError) as ctx:
            env_plate(args)
        self.assertIn("prompt", str(ctx.exception))

    def test_prompt_file_read(self):
        """prompt-file is read and used as prompt."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            prompt_file = Path(tmp) / "prompt.txt"
            prompt_file.write_text("a forest at dawn")

            mock_run = mock.MagicMock(return_value={"ok": True})
            with mock.patch("cli_motion.run_env_plate", mock_run):
                args = Namespace(
                    prompt="",
                    prompt_file=str(prompt_file),
                    root=None,
                    shot_id="s1",
                    no_wait=False,
                    width="720",
                    height="1280",
                    duration="5",
                    fps="24",
                    no_register=False,
                    no_keyframe=False,
                    out_dir=None,
                    poll_timeout=240,
                )
                result = env_plate(args)

            self.assertTrue(result["ok"])
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            self.assertEqual(call_kwargs["prompt"], "a forest at dawn")

    def test_missing_prompt_file_raises(self):
        """Non-existent prompt-file → MotionRouteError."""
        args = Namespace(prompt="", prompt_file="/nonexistent/file.txt")
        with self.assertRaises(MotionRouteError) as ctx:
            env_plate(args)
        self.assertIn("cannot read", str(ctx.exception))


class TestMotionPlanRoute(unittest.TestCase):
    """motion_plan route forwards to build_motion_plan."""

    def test_forwards_to_build_motion_plan(self):
        """Valid args → build_motion_plan called with root and shot_id."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            mock_build = mock.MagicMock(return_value={"ok": True})
            with mock.patch("cli_motion.build_motion_plan", mock_build):
                args = Namespace(root=tmp, shot_id="shot01")
                result = motion_plan(args)

            self.assertTrue(result["ok"])
            mock_build.assert_called_once_with(Path(tmp), "shot01")

    def test_motion_plan_error_wrapped(self):
        """MotionPlanError → MotionRouteError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:

            class FakeMotionPlanError(Exception):
                pass

            def raise_err(root, shot_id):
                raise FakeMotionPlanError("plan failed")

            # Patch the live module after the env-plate test reloads it.
            import cli_motion

            with (
                mock.patch.object(cli_motion, "build_motion_plan", side_effect=raise_err),
                mock.patch.object(cli_motion, "MotionPlanError", FakeMotionPlanError),
            ):
                args = Namespace(root=tmp, shot_id="shot01")
                with self.assertRaises(MotionRouteError) as ctx:
                    cli_motion.motion_plan(args)
                self.assertIn("plan failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
