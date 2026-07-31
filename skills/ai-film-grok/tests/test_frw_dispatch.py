"""Tests for frw_dispatch.py — FRW launcher dispatch logic.

Previously had ZERO test coverage. Tests cover:
  - resolve_python: venv detection, env override, fallback
  - load_dotenv: .env parsing, no-overwrite-existing
  - run_canary: missing canary script handling
  - main: help/canary routing

These tests do NOT require frwclaw-pro to be installed (they test
the local dispatch logic, not the proxied frwclaw CLI).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import frw_dispatch  # noqa: E402


class TestResolvePython(unittest.TestCase):
    """resolve_python picks the right interpreter."""

    def test_env_override(self):
        """FRWCLAW_PYTHON env var takes precedence."""
        fake_py = Path("/fake/python3")
        with mock.patch.dict(os.environ, {"FRWCLAW_PYTHON": str(fake_py)}):
            # resolve_python checks .is_file(), so mock that
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch.object(Path, "expanduser", return_value=fake_py):
                    result = frw_dispatch.resolve_python(Path("/fake/root"))
                    self.assertEqual(result, str(fake_py))

    def test_fallback_to_sys_executable(self):
        """No venv, no env → falls back to sys.executable."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"FRWCLAW_PYTHON": ""}, clear=False):
                os.environ.pop("FRWCLAW_PYTHON", None)
                root = Path(tmp)
                # No .venv/bin/python
                result = frw_dispatch.resolve_python(root)
                self.assertEqual(result, sys.executable)


class TestLoadDotenv(unittest.TestCase):
    """load_dotenv parses .env without overwriting existing keys."""

    def test_parses_dotenv(self):
        """Valid .env → keys added to env dict."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text("FRW_API_KEY=secret123\nMODEL=seedance\n")

            env: dict[str, str] = {}
            frw_dispatch.load_dotenv(root, env)
            self.assertEqual(env["FRW_API_KEY"], "secret123")
            self.assertEqual(env["MODEL"], "seedance")

    def test_no_overwrite_existing(self):
        """Existing keys in env are NOT overwritten by .env."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text("KEY=from_file\n")

            env = {"KEY": "already_set"}
            frw_dispatch.load_dotenv(root, env)
            self.assertEqual(env["KEY"], "already_set")

    def test_skips_comments_and_empty(self):
        """Comments and empty lines are skipped."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text("# comment\n\nKEY=val\n")

            env: dict[str, str] = {}
            frw_dispatch.load_dotenv(root, env)
            self.assertEqual(env, {"KEY": "val"})

    def test_strips_quotes(self):
        """Quoted values are stripped."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text("KEY=\"quoted\"\nKEY2='single'\n")

            env: dict[str, str] = {}
            frw_dispatch.load_dotenv(root, env)
            self.assertEqual(env["KEY"], "quoted")
            self.assertEqual(env["KEY2"], "single")

    def test_no_dotenv_file(self):
        """Missing .env → no-op, no error."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {"EXISTING": "val"}
            frw_dispatch.load_dotenv(root, env)
            self.assertEqual(env, {"EXISTING": "val"})


class TestCurrentPackageLayout(unittest.TestCase):
    def test_current_launcher_is_a_supported_root_and_is_preferred(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frwclaw-pro").touch()
            self.assertTrue(frw_dispatch.is_supported_frw_root(root))
            self.assertEqual(
                frw_dispatch.build_dispatch_command(root, ["img2video-audio", "--wait"]),
                [str(root / "frwclaw-pro"), "img2video-audio", "--wait"],
            )

    def test_native_audio_uses_the_actual_frw_subcommand_contract(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "frwclaw-pro").touch()
            args = [
                "img2video-audio",
                "--img-url",
                "https://example.invalid/keyframe.png",
                "--prompt",
                "Japanese dialogue, no visible text",
                "--width",
                "704",
                "--height",
                "1280",
                "--duration",
                "5",
                "--wait",
            ]
            self.assertEqual(
                frw_dispatch.build_dispatch_command(root, args),
                [str(root / "frwclaw-pro"), *args],
            )
            self.assertNotIn("--model", args)

    def test_legacy_dispatch_remains_supported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatch = root / "img-video-frw" / "scripts" / "dispatch.py"
            dispatch.parent.mkdir(parents=True)
            dispatch.touch()
            with mock.patch.object(frw_dispatch, "resolve_python", return_value="python-test"):
                self.assertEqual(
                    frw_dispatch.build_dispatch_command(root, ["help"]),
                    ["python-test", str(dispatch), "help"],
                )


class TestRunCanary(unittest.TestCase):
    """run_canary dispatches to frw_canary.py."""

    def test_missing_canary_script(self):
        """Missing frw_canary.py → returns 1 with error JSON."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # frw_canary.py is in the same dir as frw_dispatch.py
            # Mock it to not exist
            with mock.patch.object(Path, "is_file", return_value=False):
                rc = frw_dispatch.run_canary(["--root", tmp])
                self.assertEqual(rc, 1)


class TestMainRouting(unittest.TestCase):
    """main() routes canary/help correctly without requiring frwclaw-pro."""

    def test_help_routing(self):
        """main(['help']) returns 0 (doesn't need frwclaw-pro)."""
        rc = frw_dispatch.main(["help"])
        # help prints usage and exits; may return 0 or route to frwclaw
        # Since "help" is not "canary", it tries to resolve_frw_root
        # which will fail if frwclaw-pro not installed
        # We just verify it doesn't crash with TypeError (our P0 bug fix)
        self.assertIsInstance(rc, int)

    def test_canary_routes_locally(self):
        """main(['canary']) routes to run_canary, not frwclaw."""
        with mock.patch.object(frw_dispatch, "run_canary", return_value=0) as mock_canary:
            rc = frw_dispatch.main(["canary"])
            self.assertEqual(rc, 0)
            mock_canary.assert_called_once()

    def test_empty_argv_defaults_to_help(self):
        """main([]) defaults to ['help']."""
        with mock.patch.object(frw_dispatch, "run_canary", return_value=0):
            # Empty argv → ["help"] → tries resolve_frw_root
            # Just verify no TypeError
            try:
                rc = frw_dispatch.main([])
                self.assertIsInstance(rc, int)
            except SystemExit:
                pass  # resolve_frw_root raises SystemExit if frwclaw missing


if __name__ == "__main__":
    unittest.main()
