"""Regression tests for FRW subprocess return-code and timeout contracts."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
import frw_dispatch  # noqa: E402


class FrwDispatchSubprocessTests(unittest.TestCase):
    def test_canary_returns_child_exit_code_and_timeout(self) -> None:
        with mock.patch.object(frw_dispatch.Path, "is_file", return_value=True):
            with mock.patch.object(
                frw_dispatch.subprocess,
                "run",
                return_value=mock.Mock(returncode=7),
            ) as run:
                result = frw_dispatch.run_canary(["--root", "/tmp/film"])

        self.assertEqual(result, 7)
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        self.assertFalse(run.call_args.kwargs.get("check", True))

    def test_dispatch_returns_child_exit_code_and_timeout(self) -> None:
        root = Path("/tmp/frw-root")
        dispatch = root / "img-video-frw" / "scripts" / "dispatch.py"
        with mock.patch.object(frw_dispatch, "resolve_frw_root", return_value=root):
            with mock.patch.object(frw_dispatch, "resolve_python", return_value="python"):
                with mock.patch.object(frw_dispatch, "load_dotenv"):
                    with mock.patch.object(
                        frw_dispatch.subprocess,
                        "run",
                        return_value=mock.Mock(returncode=9),
                    ) as run:
                        result = frw_dispatch.main(["newvideo", "--wait"])

        self.assertEqual(result, 9)
        self.assertEqual(run.call_args.kwargs["timeout"], 60)
        self.assertEqual(run.call_args.kwargs["cwd"], str(root))

    def test_cli_frw_returns_child_exit_code_and_timeout(self) -> None:
        args = argparse.Namespace(frw_argv=["canary"])
        with mock.patch.object(
            aifilm_grok.subprocess,
            "run",
            return_value=mock.Mock(returncode=11),
        ) as run:
            result = aifilm_grok.cmd_frw(args)

        self.assertEqual(result, 11)
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        self.assertFalse(run.call_args.kwargs.get("check", True))


if __name__ == "__main__":
    unittest.main()
